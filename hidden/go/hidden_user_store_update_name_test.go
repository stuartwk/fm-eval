package shop

import "testing"

func TestHiddenUserStoreUpdateName(t *testing.T) {
	st := NewUserStore()
	st.Create(User{Email: "ada@example.com", Name: "Ada"})
	got, ok := st.UpdateName("usr_000001", "Ada Lovelace")
	if !ok || got.Name != "Ada Lovelace" || got.Email != "ada@example.com" || got.ID != "usr_000001" {
		t.Fatalf("UpdateName = %+v, %v", got, ok)
	}
	if stored, _ := st.Get("usr_000001"); stored.Name != "Ada Lovelace" {
		t.Fatalf("stored name = %q, want %q", stored.Name, "Ada Lovelace")
	}
	if _, ok := st.UpdateName("usr_000099", "Nobody"); ok {
		t.Fatal("UpdateName(missing) reported ok")
	}
}
