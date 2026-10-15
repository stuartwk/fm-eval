package shop

import (
	"slices"
	"strings"
	"sync"
)

// Review ratings are whole stars from 1 to 5.
type Review struct {
	ID        string `json:"id"`
	ProductID string `json:"product_id"`
	UserID    string `json:"user_id"`
	Rating    int    `json:"rating"`
	Body      string `json:"body"`
}

// ReviewStore is an in-memory, concurrency-safe store of reviews.
type ReviewStore struct {
	mu    sync.RWMutex
	items map[string]Review
	seq   int
}

func NewReviewStore() *ReviewStore {
	return &ReviewStore{items: make(map[string]Review)}
}

// Create assigns the next ID, stores the review, and returns the stored copy.
func (st *ReviewStore) Create(rv Review) Review {
	st.mu.Lock()
	defer st.mu.Unlock()
	st.seq++
	rv.ID = formatID("rev", st.seq)
	st.items[rv.ID] = rv
	return rv
}

func (st *ReviewStore) Get(id string) (Review, bool) {
	st.mu.RLock()
	defer st.mu.RUnlock()
	rv, ok := st.items[id]
	return rv, ok
}

// ListByProduct returns the product's reviews sorted by ID.
func (st *ReviewStore) ListByProduct(productID string) []Review {
	st.mu.RLock()
	defer st.mu.RUnlock()
	out := []Review{}
	for _, rv := range st.items {
		if rv.ProductID == productID {
			out = append(out, rv)
		}
	}
	slices.SortFunc(out, func(a, b Review) int { return strings.Compare(a.ID, b.ID) })
	return out
}
