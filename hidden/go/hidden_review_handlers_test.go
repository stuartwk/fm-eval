package shop

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// hiddenReviewRequest routes through a mux with only the review routes,
// since Server.Routes does not register them.
func hiddenReviewRequest(t *testing.T, s *Server, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	mux := http.NewServeMux()
	s.reviewRoutes(mux)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(method, path, strings.NewReader(body)))
	return rec
}

func TestHiddenCreateReview(t *testing.T) {
	tests := []struct {
		name     string
		product  string
		body     string
		wantCode int
		wantErr  string
		wantMsg  string
	}{
		{name: "ok", product: "prd_000001", body: `{"user_id":"usr_000002","rating":4,"body":"Clicky."}`, wantCode: http.StatusCreated},
		{name: "ok without body", product: "prd_000001", body: `{"user_id":"usr_000002","rating":1}`, wantCode: http.StatusCreated},
		{name: "missing product", product: "prd_000099", body: `{"user_id":"usr_000002","rating":4}`,
			wantCode: http.StatusNotFound, wantErr: codeNotFound, wantMsg: "product prd_000099 not found"},
		{name: "bad json", product: "prd_000001", body: `{"rating":`, wantCode: http.StatusBadRequest, wantErr: codeBadJSON},
		{name: "unknown field", product: "prd_000001", body: `{"user_id":"usr_000002","rating":4,"stars":4}`, wantCode: http.StatusBadRequest, wantErr: codeBadJSON},
		{name: "missing user", product: "prd_000001", body: `{"rating":4}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "rating zero", product: "prd_000001", body: `{"user_id":"usr_000002","rating":0}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "rating six", product: "prd_000001", body: `{"user_id":"usr_000002","rating":6}`, wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "body too long", product: "prd_000001", body: `{"user_id":"usr_000002","rating":3,"body":"` + strings.Repeat("x", 501) + `"}`,
			wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed},
		{name: "unknown user", product: "prd_000001", body: `{"user_id":"usr_000099","rating":4}`,
			wantCode: http.StatusUnprocessableEntity, wantErr: codeValidationFailed, wantMsg: "user_id: unknown user"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := newTestServer(t)
			rec := hiddenReviewRequest(t, s, "POST", "/products/"+tt.product+"/reviews", tt.body)
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				var env errorEnvelope
				json.Unmarshal(rec.Body.Bytes(), &env)
				if env.Error.Code != tt.wantErr || (tt.wantMsg != "" && env.Error.Message != tt.wantMsg) {
					t.Fatalf("error = %+v, want code %q message %q", env.Error, tt.wantErr, tt.wantMsg)
				}
				return
			}
			got := decodeData[Review](t, rec)
			if got.ID != "rev_000001" || got.ProductID != tt.product || got.UserID != "usr_000002" {
				t.Fatalf("got %+v", got)
			}
			if _, ok := s.reviews.Get("rev_000001"); !ok {
				t.Fatal("review was not stored")
			}
		})
	}
}

func TestHiddenListProductReviews(t *testing.T) {
	s := newTestServer(t)
	s.reviews.Create(Review{ProductID: "prd_000001", UserID: "usr_000001", Rating: 5})
	s.reviews.Create(Review{ProductID: "prd_000003", UserID: "usr_000001", Rating: 2})
	s.reviews.Create(Review{ProductID: "prd_000001", UserID: "usr_000002", Rating: 4})

	tests := []struct {
		name     string
		path     string
		wantCode int
		wantErr  string
		wantIDs  []string
		wantPage pageInfo
	}{
		{name: "filters by product", path: "/products/prd_000001/reviews", wantCode: http.StatusOK,
			wantIDs: []string{"rev_000001", "rev_000003"}, wantPage: pageInfo{Limit: 20, Total: 2}},
		{name: "paginates", path: "/products/prd_000001/reviews?limit=1&offset=1", wantCode: http.StatusOK,
			wantIDs: []string{"rev_000003"}, wantPage: pageInfo{Limit: 1, Offset: 1, Total: 2}},
		{name: "no reviews", path: "/products/prd_000002/reviews", wantCode: http.StatusOK,
			wantIDs: []string{}, wantPage: pageInfo{Limit: 20, Total: 0}},
		{name: "missing product", path: "/products/prd_000099/reviews", wantCode: http.StatusNotFound, wantErr: codeNotFound},
		{name: "bad query", path: "/products/prd_000001/reviews?limit=x", wantCode: http.StatusBadRequest, wantErr: codeBadQuery},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rec := hiddenReviewRequest(t, s, "GET", tt.path, "")
			assertStatus(t, rec, tt.wantCode)
			if tt.wantErr != "" {
				if got := errorCode(t, rec); got != tt.wantErr {
					t.Fatalf("error code = %q, want %q", got, tt.wantErr)
				}
				return
			}
			reviews, page := decodeList[Review](t, rec)
			if page != tt.wantPage || len(reviews) != len(tt.wantIDs) {
				t.Fatalf("got %d reviews, page %+v; want %d, %+v", len(reviews), page, len(tt.wantIDs), tt.wantPage)
			}
			for i, rv := range reviews {
				if rv.ID != tt.wantIDs[i] {
					t.Fatalf("reviews[%d].ID = %q, want %q", i, rv.ID, tt.wantIDs[i])
				}
			}
		})
	}
}
