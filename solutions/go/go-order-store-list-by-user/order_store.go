package shop

import (
	"slices"
	"strings"
	"sync"
)

const (
	orderPending   = "pending"
	orderPaid      = "paid"
	orderCancelled = "cancelled"
)

type OrderItem struct {
	ProductID string `json:"product_id"`
	Quantity  int    `json:"quantity"`
}

type Order struct {
	ID         string      `json:"id"`
	UserID     string      `json:"user_id"`
	Items      []OrderItem `json:"items"`
	TotalCents int64       `json:"total_cents"`
	Status     string      `json:"status"`
}

// OrderStore is an in-memory, concurrency-safe store of orders.
type OrderStore struct {
	mu    sync.RWMutex
	items map[string]Order
	seq   int
}

func NewOrderStore() *OrderStore {
	return &OrderStore{items: make(map[string]Order)}
}

// Create assigns the next ID, stores the order, and returns the stored copy.
func (st *OrderStore) Create(o Order) Order {
	st.mu.Lock()
	defer st.mu.Unlock()
	st.seq++
	o.ID = formatID("ord", st.seq)
	o.Items = slices.Clone(o.Items)
	st.items[o.ID] = o
	return o
}

func (st *OrderStore) Get(id string) (Order, bool) {
	st.mu.RLock()
	defer st.mu.RUnlock()
	o, ok := st.items[id]
	return o, ok
}

// SetStatus reports whether the order existed.
func (st *OrderStore) SetStatus(id, status string) (Order, bool) {
	st.mu.Lock()
	defer st.mu.Unlock()
	o, ok := st.items[id]
	if !ok {
		return Order{}, false
	}
	o.Status = status
	st.items[id] = o
	return o, true
}

// List returns all orders sorted by ID.
func (st *OrderStore) List() []Order {
	st.mu.RLock()
	defer st.mu.RUnlock()
	out := make([]Order, 0, len(st.items))
	for _, o := range st.items {
		out = append(out, o)
	}
	slices.SortFunc(out, func(a, b Order) int { return strings.Compare(a.ID, b.ID) })
	return out
}

// ListByUser returns the user's orders sorted by ID.
func (st *OrderStore) ListByUser(userID string) []Order {
	st.mu.RLock()
	defer st.mu.RUnlock()
	out := []Order{}
	for _, o := range st.items {
		if o.UserID == userID {
			out = append(out, o)
		}
	}
	slices.SortFunc(out, func(a, b Order) int { return strings.Compare(a.ID, b.ID) })
	return out
}
