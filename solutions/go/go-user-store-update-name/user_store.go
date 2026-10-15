package shop

import (
	"slices"
	"strings"
	"sync"
)

type User struct {
	ID    string `json:"id"`
	Email string `json:"email"`
	Name  string `json:"name"`
}

// UserStore is an in-memory, concurrency-safe store of users.
type UserStore struct {
	mu    sync.RWMutex
	items map[string]User
	seq   int
}

func NewUserStore() *UserStore {
	return &UserStore{items: make(map[string]User)}
}

// Create assigns the next ID, stores the user, and returns the stored copy.
func (st *UserStore) Create(u User) User {
	st.mu.Lock()
	defer st.mu.Unlock()
	st.seq++
	u.ID = formatID("usr", st.seq)
	st.items[u.ID] = u
	return u
}

func (st *UserStore) Get(id string) (User, bool) {
	st.mu.RLock()
	defer st.mu.RUnlock()
	u, ok := st.items[id]
	return u, ok
}

// FindByEmail matches case-insensitively.
func (st *UserStore) FindByEmail(email string) (User, bool) {
	st.mu.RLock()
	defer st.mu.RUnlock()
	for _, u := range st.items {
		if strings.EqualFold(u.Email, email) {
			return u, true
		}
	}
	return User{}, false
}

// List returns all users sorted by ID.
func (st *UserStore) List() []User {
	st.mu.RLock()
	defer st.mu.RUnlock()
	out := make([]User, 0, len(st.items))
	for _, u := range st.items {
		out = append(out, u)
	}
	slices.SortFunc(out, func(a, b User) int { return strings.Compare(a.ID, b.ID) })
	return out
}

// Delete reports whether the user existed.
func (st *UserStore) Delete(id string) bool {
	st.mu.Lock()
	defer st.mu.Unlock()
	if _, ok := st.items[id]; !ok {
		return false
	}
	delete(st.items, id)
	return true
}

// UpdateName reports whether the user existed.
func (st *UserStore) UpdateName(id, name string) (User, bool) {
	st.mu.Lock()
	defer st.mu.Unlock()
	u, ok := st.items[id]
	if !ok {
		return User{}, false
	}
	u.Name = name
	st.items[id] = u
	return u, true
}
