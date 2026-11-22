package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strings"
	"time"
)

const (
	ocrPath = "/ocr"
	// ocrTimeout bounds one POST /ocr call; Tesseract on a large screenshot takes a few seconds on CPU.
	ocrTimeout = 25 * time.Second
	// maxImageBytes is the upload limit for POST /api/check/image (the same limit rag enforces).
	maxImageBytes = 5 << 20
	// maxOCRBodyBytes caps rag's answer so a broken service cannot exhaust memory.
	maxOCRBodyBytes = 1 << 20
	imageFormField  = "image"
)

// Errors from rag's OCR, mapped to statuses by the image handler.
var (
	errOCRRejected    = errors.New("image rejected")  // 422: not an image, too large, no readable text -> needs_clarification
	errOCRUnavailable = errors.New("ocr unavailable") // transport, timeout, 5xx -> technical_error
)

// ocrResult is rag's answer to POST /ocr (CONTRACT.md section 3): text read locally by Tesseract.
type ocrResult struct {
	Text       string   `json:"text"`
	Confidence float64  `json:"confidence"`
	Dates      []string `json:"dates"`
	Engine     string   `json:"engine"`
}

// ocrClient sends an uploaded image to rag and returns the text; the image is never stored on either side.
type ocrClient struct {
	baseURL string
	client  *http.Client
}

func newOCRClient(ragBaseURL string, timeout time.Duration) *ocrClient {
	return &ocrClient{baseURL: strings.TrimRight(ragBaseURL, "/"), client: &http.Client{Timeout: timeout}}
}

func (c *ocrClient) read(ctx context.Context, image []byte, filename, contentType string) (ocrResult, error) {
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	part, err := form.CreatePart(map[string][]string{
		"Content-Disposition": {fmt.Sprintf(`form-data; name="%s"; filename="%s"`, imageFormField, filename)},
		"Content-Type":        {contentType},
	})
	if err != nil {
		return ocrResult{}, fmt.Errorf("build ocr form: %w", err)
	}
	if _, err := part.Write(image); err != nil {
		return ocrResult{}, fmt.Errorf("write ocr form: %w", err)
	}
	if err := form.Close(); err != nil {
		return ocrResult{}, fmt.Errorf("close ocr form: %w", err)
	}

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+ocrPath, &body)
	if err != nil {
		return ocrResult{}, fmt.Errorf("build ocr request: %w", err)
	}
	request.Header.Set("Content-Type", form.FormDataContentType())
	response, err := c.client.Do(request)
	if err != nil {
		return ocrResult{}, fmt.Errorf("%w: %w", errOCRUnavailable, err)
	}
	defer response.Body.Close()
	answer, err := io.ReadAll(io.LimitReader(response.Body, maxOCRBodyBytes))
	if err != nil {
		return ocrResult{}, fmt.Errorf("%w: read ocr response: %w", errOCRUnavailable, err)
	}
	switch response.StatusCode {
	case http.StatusOK:
		var result ocrResult
		if err := json.Unmarshal(answer, &result); err != nil {
			return ocrResult{}, fmt.Errorf("%w: decode ocr response: %w", errOCRUnavailable, err)
		}
		return result, nil
	case http.StatusUnprocessableEntity:
		return ocrResult{}, fmt.Errorf("%w: %s", errOCRRejected, strings.TrimSpace(string(answer)))
	default:
		return ocrResult{}, fmt.Errorf("%w: ocr HTTP %d", errOCRUnavailable, response.StatusCode)
	}
}
