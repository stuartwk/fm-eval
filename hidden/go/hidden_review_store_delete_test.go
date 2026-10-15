package shop

import "testing"

func TestHiddenReviewStoreDelete(t *testing.T) {
	st := NewReviewStore()
	st.Create(Review{ProductID: "prd_000001", UserID: "usr_000001", Rating: 5})
	st.Create(Review{ProductID: "prd_000001", UserID: "usr_000002", Rating: 3})
	if !st.Delete("rev_000001") {
		t.Fatal("Delete(rev_000001) = false, want true")
	}
	if _, ok := st.Get("rev_000001"); ok {
		t.Fatal("deleted review is still returned by Get")
	}
	if got := st.ListByProduct("prd_000001"); len(got) != 1 || got[0].ID != "rev_000002" {
		t.Fatalf("ListByProduct after delete = %+v", got)
	}
	if st.Delete("rev_000001") {
		t.Fatal("second Delete(rev_000001) = true, want false")
	}
	if st.Delete("rev_000099") {
		t.Fatal("Delete(missing) = true, want false")
	}
}
