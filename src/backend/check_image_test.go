package main

import (
	"bytes"
	"context"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"prawdowid/agent"
)

// pngHeader is the start of a PNG file, enough for http.DetectContentType to call it image/png.
var pngHeader = []byte("\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

func multipartImage(t *testing.T, field, filename string, content []byte) (*bytes.Buffer, string) {
	t.Helper()
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	part, err := form.CreateFormFile(field, filename)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := part.Write(content); err != nil {
		t.Fatal(err)
	}
	if err := form.Close(); err != nil {
		t.Fatal(err)
	}
	return &body, form.FormDataContentType()
}

func postImage(handlers *checkHandlers, body *bytes.Buffer, contentType string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodPost, "/api/check/image", body)
	request.Header.Set("Content-Type", contentType)
	recorder := httptest.NewRecorder()
	handlers.checkImage(recorder, request)
	return recorder
}

func fakeOCR(t *testing.T, status int, answer string) *ocrClient {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseMultipartForm(maxImageBytes); err != nil {
			t.Errorf("ocr request is not multipart: %v", err)
		}
		if _, _, err := r.FormFile(imageFormField); err != nil {
			t.Errorf("ocr request has no image field: %v", err)
		}
		w.WriteHeader(status)
		_, _ = w.Write([]byte(answer))
	}))
	t.Cleanup(server.Close)
	return newOCRClient(server.URL, 2*time.Second)
}

func TestImageCheckRunsOCRTextThroughTheSamePipeline(t *testing.T) {
	var seen agent.VerifyRequest
	handlers, saved := newTestHandlers(func(_ context.Context, request agent.VerifyRequest) (agent.CheckResult, error) {
		seen = request
		return agent.CheckResult{RequestID: request.RequestID, Status: agent.StatusOK, Limitations: []string{"z agenta"}}, nil
	}, 10)
	handlers.ocr = fakeOCR(t, http.StatusOK, `{"text":"Strajk 20.11.2026, tel 600 700 800","confidence":0.9,"dates":["20.11.2026"],"engine":"tesseract"}`)

	body, contentType := multipartImage(t, imageFormField, "shot.png", pngHeader)
	recorder := postImage(handlers, body, contentType)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status %d, body %s", recorder.Code, recorder.Body.String())
	}
	result := decodeResult(t, recorder)
	if result.Status != agent.StatusOK {
		t.Fatalf("status %s: %s", result.Status, recorder.Body.String())
	}
	if seen.InputType != inputTypeImage || !strings.Contains(seen.Input, "[ukryto]") || strings.Contains(seen.Input, "600 700 800") {
		t.Fatalf("agent should get masked OCR text as image input: %+v", seen)
	}
	if len(*saved) != 1 || (*saved)[0].InputType != inputTypeImage {
		t.Fatalf("stored run: %+v", *saved)
	}
	joined := strings.Join(result.Limitations, "\n")
	for _, want := range []string{"OCR", "20.11.2026", "z agenta"} {
		if !strings.Contains(joined, want) {
			t.Fatalf("limitations missing %q: %v", want, result.Limitations)
		}
	}
	var raw map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &raw); err != nil {
		t.Fatal(err)
	}
	if _, ok := raw["summary"]; !ok {
		t.Fatal("image answer must have the same shape as a text answer (summary field)")
	}
}

func TestImageCheckRejectsBadUploadsWithoutOCR(t *testing.T) {
	tests := []struct {
		name     string
		field    string
		content  []byte
		wantText string
	}{
		{"wrong field", "file", pngHeader, messageImageMissing},
		{"not an image", imageFormField, []byte("%PDF-1.4 hello"), messageImageUnsupported},
		{"empty", imageFormField, []byte{}, messageImageMissing},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			handlers, _ := newTestHandlers(func(context.Context, agent.VerifyRequest) (agent.CheckResult, error) {
				t.Fatal("agent must not be called")
				return agent.CheckResult{}, nil
			}, 10)
			handlers.ocr = fakeOCR(t, http.StatusOK, `{}`)
			body, contentType := multipartImage(t, test.field, "x.bin", test.content)
			recorder := postImage(handlers, body, contentType)
			result := decodeResult(t, recorder)
			if recorder.Code != http.StatusOK || result.Status != agent.StatusNeedsClarification || *result.Message != test.wantText {
				t.Fatalf("got %d %s %v", recorder.Code, result.Status, result.Message)
			}
		})
	}
}

func TestImageCheckMapsOCRFailures(t *testing.T) {
	unreadable, _ := newTestHandlers(okVerify, 10)
	unreadable.ocr = fakeOCR(t, http.StatusUnprocessableEntity, `{"detail":"Nie udało się odczytać obrazu: no readable text."}`)
	body, contentType := multipartImage(t, imageFormField, "shot.png", pngHeader)
	result := decodeResult(t, postImage(unreadable, body, contentType))
	if result.Status != agent.StatusNeedsClarification || *result.Message != messageImageUnreadable {
		t.Fatalf("422 from ocr must be needs_clarification: %+v", result)
	}

	down, _ := newTestHandlers(okVerify, 10)
	down.ocr = fakeOCR(t, http.StatusServiceUnavailable, `{}`)
	body, contentType = multipartImage(t, imageFormField, "shot.png", pngHeader)
	recorder := postImage(down, body, contentType)
	result = decodeResult(t, recorder)
	if recorder.Code != http.StatusServiceUnavailable || result.Status != agent.StatusTechnicalError || !strings.Contains(*result.Message, "nie ocena treści") {
		t.Fatalf("ocr outage must be technical_error: %d %+v", recorder.Code, result)
	}
}
