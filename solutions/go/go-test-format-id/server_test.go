package shop

import "testing"

func TestFormatID(t *testing.T) {
	tests := []struct {
		name   string
		prefix string
		n      int
		want   string
	}{
		{name: "one", prefix: "usr", n: 1, want: "usr_000001"},
		{name: "zero", prefix: "ord", n: 0, want: "ord_000000"},
		{name: "six digits", prefix: "prd", n: 123456, want: "prd_123456"},
		{name: "seven digits", prefix: "rev", n: 1234567, want: "rev_1234567"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := formatID(tt.prefix, tt.n); got != tt.want {
				t.Fatalf("formatID(%q, %d) = %q, want %q", tt.prefix, tt.n, got, tt.want)
			}
		})
	}
}
