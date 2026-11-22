package main

import (
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"unicode/utf8"

	"prawdowid/agent"
)

// inputTypeImage marks a run that started from an uploaded picture; the agent itself only sees the text read
// from it, so for the agent this is text input (CONTRACT.md section 1, brief scenario F).
const (
	inputTypeImage = "image"
	// multipartOverheadBytes covers the form boundaries and headers around the image itself.
	multipartOverheadBytes = 64 << 10
)

// Messages for the citizen (simple Polish); technical detail goes to the log.
const (
	messageImageMissing        = "Dodaj zrzut ekranu albo zdjęcie w formacie PNG, JPEG lub WEBP."
	messageImageTooLarge       = "Obraz jest za duży. Wybierz plik do 5 MB."
	messageImageUnsupported    = "Nieobsługiwany rodzaj pliku. Dodaj obraz PNG, JPEG albo WEBP."
	messageImageUnreadable     = "Nie udało się odczytać tekstu z tego obrazu. Wpisz treść do sprawdzenia ręcznie."
	messageImageOCRUnavailable = "Odczyt tekstu z obrazu jest chwilowo niedostępny. To problem techniczny, nie ocena treści. " +
		"Wpisz treść ręcznie albo spróbuj za chwilę."

	limitationImageOCR = "Tekst odczytano automatycznie z obrazu (OCR, Tesseract), więc mogą w nim być błędy odczytu. " +
		"Nie sprawdzamy, czy obraz jest autentyczny, skąd pochodzi ani czy był wcześniej publikowany."
	limitationImageDates = "Na obrazie widać datę: %s. To data w treści obrazu, nie potwierdzona data publikacji " +
		"ani wykonania zrzutu."
	limitationImageTextCut = "Z obrazu odczytano więcej tekstu, niż sprawdzamy; oceniono pierwsze 5000 znaków."
)

var supportedImageTypes = map[string]struct{}{
	"image/png":  {},
	"image/jpeg": {},
	"image/webp": {},
}

// checkImage is the web channel for a screenshot or photo (brief scenario F). The picture goes to rag's local OCR,
// the text comes back through the same runCheck pipeline as typed text, and the answer says plainly that the text
// came from OCR and that a date seen on the image proves nothing about publication.
func (h *checkHandlers) checkImage(writer http.ResponseWriter, request *http.Request) {
	requestID, early, statusCode, ok := h.beginCheck(request, webChannel)
	if !ok {
		h.reply(writer, statusCode, early)
		return
	}
	if h.ocr == nil {
		h.logger.Error("image check without an OCR client", "requestId", requestID)
		h.reply(writer, http.StatusServiceUnavailable, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageImageOCRUnavailable))
		return
	}

	request.Body = http.MaxBytesReader(writer, request.Body, maxImageBytes+multipartOverheadBytes)
	image, filename, contentType, message := readUploadedImage(request)
	if message != "" {
		h.reply(writer, http.StatusOK, h.nonMerit(requestID, webChannel, agent.StatusNeedsClarification, message))
		return
	}

	read, err := h.ocr.read(request.Context(), image, filename, contentType)
	if err != nil {
		if errors.Is(err, errOCRRejected) {
			h.logger.Warn("image rejected by ocr", "requestId", requestID, "error", err)
			h.reply(writer, http.StatusOK, h.nonMerit(requestID, webChannel, agent.StatusNeedsClarification, messageImageUnreadable))
			return
		}
		h.logger.Error("ocr unavailable", "requestId", requestID, "error", err)
		h.reply(writer, http.StatusServiceUnavailable, h.nonMerit(requestID, webChannel, agent.StatusTechnicalError, messageImageOCRUnavailable))
		return
	}
	h.logger.Info("image text read", "requestId", requestID, "engine", read.Engine, "confidence", read.Confidence,
		"chars", utf8.RuneCountInString(read.Text), "dates", len(read.Dates))

	text := strings.TrimSpace(read.Text)
	if text == "" {
		h.reply(writer, http.StatusOK, h.nonMerit(requestID, webChannel, agent.StatusNeedsClarification, messageImageUnreadable))
		return
	}
	limitations := []string{limitationImageOCR}
	if utf8.RuneCountInString(text) > maxInputRunes {
		text = string([]rune(text)[:maxInputRunes])
		limitations = append(limitations, limitationImageTextCut)
	}
	if len(read.Dates) > 0 {
		limitations = append(limitations, fmt.Sprintf(limitationImageDates, strings.Join(read.Dates, ", ")))
	}

	result, statusCode := h.runCheck(request.Context(), requestID, webChannel, text, inputTypeImage, limitations...)
	response := h.withSummary(result)
	response.Cases = h.cases.track(request.Context(), result)
	writeJSON(h.logger, writer, statusCode, response)
}

// readUploadedImage returns the bytes of the "image" form field, or the message for the citizen when the upload
// is missing, too large or not a PNG, JPEG or WEBP (checked by content sniffing, not by the declared type).
func readUploadedImage(request *http.Request) (image []byte, filename, contentType, message string) {
	if err := request.ParseMultipartForm(maxImageBytes); err != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			return nil, "", "", messageImageTooLarge
		}
		return nil, "", "", messageImageMissing
	}
	file, header, err := request.FormFile(imageFormField)
	if err != nil {
		return nil, "", "", messageImageMissing
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxImageBytes+1))
	if err != nil {
		return nil, "", "", messageImageMissing
	}
	if len(data) > maxImageBytes {
		return nil, "", "", messageImageTooLarge
	}
	if len(data) == 0 {
		return nil, "", "", messageImageMissing
	}
	sniffed := http.DetectContentType(data)
	if _, supported := supportedImageTypes[sniffed]; !supported {
		return nil, "", "", messageImageUnsupported
	}
	return data, header.Filename, sniffed, ""
}
