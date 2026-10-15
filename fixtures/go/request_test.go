package shop

import (
	"net/http/httptest"
	"testing"
)

func TestParsePage(t *testing.T) {
	tests := []struct {
		name    string
		query   string
		want    pageParams
		wantErr bool
	}{
		{name: "defaults", query: "", want: pageParams{Limit: defaultLimit}},
		{name: "both", query: "?limit=5&offset=10", want: pageParams{Limit: 5, Offset: 10}},
		{name: "max limit", query: "?limit=100", want: pageParams{Limit: 100}},
		{name: "limit too big", query: "?limit=101", wantErr: true},
		{name: "limit zero", query: "?limit=0", wantErr: true},
		{name: "limit not a number", query: "?limit=ten", wantErr: true},
		{name: "negative offset", query: "?offset=-1", wantErr: true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			r := httptest.NewRequest("GET", "/x"+tt.query, nil)
			got, err := parsePage(r)
			if (err != nil) != tt.wantErr {
				t.Fatalf("err = %v, wantErr %v", err, tt.wantErr)
			}
			if !tt.wantErr && got != tt.want {
				t.Fatalf("got %+v, want %+v", got, tt.want)
			}
		})
	}
}

func TestPaginate(t *testing.T) {
	items := []int{1, 2, 3, 4, 5}
	tests := []struct {
		name string
		p    pageParams
		want []int
	}{
		{name: "first page", p: pageParams{Limit: 2}, want: []int{1, 2}},
		{name: "last partial", p: pageParams{Limit: 2, Offset: 4}, want: []int{5}},
		{name: "past end", p: pageParams{Limit: 2, Offset: 9}, want: []int{}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, info := paginate(items, tt.p)
			if len(got) != len(tt.want) || info.Total != 5 {
				t.Fatalf("got %v, info %+v", got, info)
			}
			for i := range got {
				if got[i] != tt.want[i] {
					t.Fatalf("got %v, want %v", got, tt.want)
				}
			}
		})
	}
}
