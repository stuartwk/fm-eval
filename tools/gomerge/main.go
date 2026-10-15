// gomerge merges a snippet of Go declarations into an existing Go file.
//
// Usage: gomerge [-additive] BASE_FILE SNIPPET_FILE [OTHER_PACKAGE_FILE...] > merged.go
//
// Every top-level declaration in the snippet replaces the base declaration
// with the same key (function name plus receiver type, or type/const/var
// name) or is appended if no such declaration exists. Imports are unioned.
// Base declarations the snippet does not mention are kept unchanged. The
// result is gofmt'ed. Exit status 2 means the snippet or base did not parse.
//
// Snippet declarations whose key matches a declaration in one of the other
// package files are dropped (small models tend to echo context code), and
// their keys are reported on stderr as "dropped: KEY".
//
// With -additive, a replaced function whose base and snippet bodies are both
// made only of call statements (registration-style, e.g. a routes function)
// keeps every base statement and appends the snippet's new ones, so a model
// that rewrites such a function cannot drop or forget existing lines.
package main

import (
	"fmt"
	"go/ast"
	"go/format"
	"go/parser"
	"go/token"
	"os"
	"sort"
	"strings"
)

func main() {
	args := os.Args[1:]
	additive := len(args) > 0 && args[0] == "-additive"
	if additive {
		args = args[1:]
	}
	if len(args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: gomerge [-additive] BASE_FILE SNIPPET_FILE [OTHER_PACKAGE_FILE...]")
		os.Exit(1)
	}
	base, err := os.ReadFile(args[0])
	check(err, "read base")
	snippet, err := os.ReadFile(args[1])
	check(err, "read snippet")
	elsewhere := map[string]bool{}
	for _, path := range args[2:] {
		src, err := os.ReadFile(path)
		check(err, "read "+path)
		f, fset, err := parse(string(src))
		check(err, "parse "+path)
		for _, d := range decls(f, fset, string(src)) {
			for _, k := range d.keys {
				elsewhere[k] = true
			}
		}
	}
	out, err := merge(string(base), string(snippet), elsewhere, additive)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	os.Stdout.WriteString(out)
}

func check(err error, what string) {
	if err != nil {
		fmt.Fprintf(os.Stderr, "%s: %v\n", what, err)
		os.Exit(1)
	}
}

// decl is one top-level declaration with its source text, including its doc comment.
type decl struct {
	keys  []string
	start int
	end   int
	text  string
	// For functions whose body is only call statements: the source before
	// the body's opening brace, and each statement's source.
	header string
	calls  []string
}

func merge(base, snippet string, elsewhere map[string]bool, additive bool) (string, error) {
	baseFile, baseFset, err := parse(base)
	if err != nil {
		return "", fmt.Errorf("base: %v", err)
	}
	pkg := baseFile.Name.Name
	if !strings.HasPrefix(strings.TrimSpace(stripComments(snippet)), "package ") {
		snippet = "package " + pkg + "\n\n" + snippet
	}
	snipFile, snipFset, err := parse(snippet)
	if err != nil {
		return "", fmt.Errorf("snippet: %v", err)
	}

	baseDecls := decls(baseFile, baseFset, base)
	snipDecls := decls(snipFile, snipFset, snippet)

	// Replace matching declarations, collecting the rest to append.
	type repl struct {
		start, end int
		text       string
	}
	var repls []repl
	var appended []string
	used := map[int]bool{}
	for _, sd := range snipDecls {
		if dup := firstIn(sd.keys, elsewhere); dup != "" {
			fmt.Fprintln(os.Stderr, "dropped: "+dup)
			continue
		}
		idx := -1
		for i, bd := range baseDecls {
			if !used[i] && overlaps(bd.keys, sd.keys) {
				idx = i
				break
			}
		}
		if idx < 0 {
			appended = append(appended, sd.text)
			continue
		}
		used[idx] = true
		text := sd.text
		if bd := baseDecls[idx]; additive && bd.calls != nil && sd.calls != nil {
			text = unionCalls(sd.header, bd.calls, sd.calls)
		}
		repls = append(repls, repl{baseDecls[idx].start, baseDecls[idx].end, text})
	}

	// Rebuild the import block as the union of both files' imports.
	imports := importSpecs(baseFile, base)
	for _, s := range importSpecs(snipFile, snippet) {
		if !contains(imports, s) {
			imports = append(imports, s)
		}
	}
	sort.Strings(imports)
	importStart, importEnd := importRange(baseFile, baseFset)

	out := base
	edits := repls
	if importEnd > 0 {
		edits = append(edits, repl{importStart, importEnd, importBlock(imports)})
	}
	sort.Slice(edits, func(i, j int) bool { return edits[i].start > edits[j].start })
	for _, e := range edits {
		out = out[:e.start] + e.text + out[e.end:]
	}
	if importEnd == 0 && len(imports) > 0 {
		// Base had no imports: insert after the package clause.
		pkgEnd := baseFset.Position(baseFile.Name.End()).Offset
		out = out[:pkgEnd] + "\n\n" + importBlock(imports) + out[pkgEnd:]
	}
	for _, t := range appended {
		out = strings.TrimRight(out, "\n") + "\n\n" + t + "\n"
	}
	formatted, err := format.Source([]byte(out))
	if err != nil {
		return "", fmt.Errorf("format merged file: %v", err)
	}
	return string(formatted), nil
}

func parse(src string) (*ast.File, *token.FileSet, error) {
	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, "x.go", src, parser.ParseComments)
	return f, fset, err
}

func decls(f *ast.File, fset *token.FileSet, src string) []decl {
	var out []decl
	for _, d := range f.Decls {
		if g, ok := d.(*ast.GenDecl); ok && g.Tok == token.IMPORT {
			continue
		}
		var doc *ast.CommentGroup
		var keys []string
		switch d := d.(type) {
		case *ast.FuncDecl:
			doc = d.Doc
			keys = []string{"func " + recvType(d) + d.Name.Name}
		case *ast.GenDecl:
			doc = d.Doc
			for _, s := range d.Specs {
				switch s := s.(type) {
				case *ast.TypeSpec:
					keys = append(keys, "name "+s.Name.Name)
				case *ast.ValueSpec:
					for _, n := range s.Names {
						keys = append(keys, "name "+n.Name)
					}
				}
			}
		}
		start := fset.Position(d.Pos()).Offset
		if doc != nil {
			start = fset.Position(doc.Pos()).Offset
		}
		end := fset.Position(d.End()).Offset
		dl := decl{keys: keys, start: start, end: end, text: src[start:end]}
		if fn, ok := d.(*ast.FuncDecl); ok && fn.Body != nil {
			dl.header, dl.calls = callBody(fn, fset, src, start)
		}
		out = append(out, dl)
	}
	return out
}

// callBody returns the function's header and its statements' source if the
// body is non-empty and made only of call expression statements.
func callBody(fn *ast.FuncDecl, fset *token.FileSet, src string, start int) (string, []string) {
	if len(fn.Body.List) == 0 {
		return "", nil
	}
	var calls []string
	for _, st := range fn.Body.List {
		es, ok := st.(*ast.ExprStmt)
		if !ok {
			return "", nil
		}
		if _, ok := es.X.(*ast.CallExpr); !ok {
			return "", nil
		}
		calls = append(calls, src[fset.Position(st.Pos()).Offset:fset.Position(st.End()).Offset])
	}
	return src[start:fset.Position(fn.Body.Lbrace).Offset], calls
}

// unionCalls builds a function from header with every base call, followed by
// the snippet calls that are not already present. A snippet call with the
// same callee and first argument as a base call (for example the same route
// pattern) replaces that call instead of being added, so a route can be
// re-pointed without registering it twice.
func unionCalls(header string, base, snippet []string) string {
	norm := func(s string) string { return strings.Join(strings.Fields(s), "") }
	key := func(s string) string {
		n := norm(s)
		if i := strings.Index(n, ","); i >= 0 {
			return n[:i]
		}
		return n
	}
	byKey := map[string]string{}
	for _, c := range snippet {
		byKey[key(c)] = c
	}
	used := map[string]bool{}
	var out []string
	for _, c := range base {
		if s, ok := byKey[key(c)]; ok {
			out = append(out, s)
			used[key(c)] = true
			continue
		}
		out = append(out, c)
	}
	for _, c := range snippet {
		if !used[key(c)] {
			used[key(c)] = true
			out = append(out, c)
		}
	}
	return header + "{\n\t" + strings.Join(out, "\n\t") + "\n}"
}

func recvType(f *ast.FuncDecl) string {
	if f.Recv == nil || len(f.Recv.List) == 0 {
		return ""
	}
	t := f.Recv.List[0].Type
	if s, ok := t.(*ast.StarExpr); ok {
		t = s.X
	}
	if id, ok := t.(*ast.Ident); ok {
		return id.Name + "."
	}
	return "?."
}

func importSpecs(f *ast.File, src string) []string {
	var out []string
	for _, s := range f.Imports {
		out = append(out, src[s.Pos()-1:s.End()-1])
	}
	return out
}

func importRange(f *ast.File, fset *token.FileSet) (int, int) {
	start, end := -1, 0
	for _, d := range f.Decls {
		if g, ok := d.(*ast.GenDecl); ok && g.Tok == token.IMPORT {
			if start < 0 {
				start = fset.Position(g.Pos()).Offset
			}
			end = fset.Position(g.End()).Offset
		}
	}
	if start < 0 {
		return 0, 0
	}
	return start, end
}

func importBlock(specs []string) string {
	if len(specs) == 0 {
		return ""
	}
	return "import (\n\t" + strings.Join(specs, "\n\t") + "\n)"
}

func firstIn(keys []string, set map[string]bool) string {
	for _, k := range keys {
		if set[k] {
			return k
		}
	}
	return ""
}

func overlaps(a, b []string) bool {
	for _, x := range a {
		if contains(b, x) {
			return true
		}
	}
	return false
}

func contains(xs []string, x string) bool {
	for _, y := range xs {
		if y == x {
			return true
		}
	}
	return false
}

// stripComments removes leading // and /* */ comments so a snippet that
// starts with a comment before its package clause is detected correctly.
func stripComments(s string) string {
	for {
		t := strings.TrimSpace(s)
		switch {
		case strings.HasPrefix(t, "//"):
			if i := strings.Index(t, "\n"); i >= 0 {
				s = t[i+1:]
				continue
			}
			return ""
		case strings.HasPrefix(t, "/*"):
			if i := strings.Index(t, "*/"); i >= 0 {
				s = t[i+2:]
				continue
			}
			return ""
		}
		return t
	}
}
