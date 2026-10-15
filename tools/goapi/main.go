// goapi prints a compact API reference for a Go package directory: every
// function and method signature, struct and type definitions, and constants,
// each with the first line of its doc comment. It is the generated version
// of a hand-written cheat sheet skill.
//
// Usage: goapi [-skip FILE]... DIR > api.md
//
// -skip omits a file (the task's target, which the model sees in full).
package main

import (
	"bytes"
	"fmt"
	"go/ast"
	"go/parser"
	"go/printer"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func main() {
	args := os.Args[1:]
	skip := map[string]bool{}
	for len(args) >= 2 && args[0] == "-skip" {
		skip[args[1]] = true
		args = args[2:]
	}
	if len(args) != 1 {
		fmt.Fprintln(os.Stderr, "usage: goapi [-skip FILE]... DIR")
		os.Exit(1)
	}
	dir := args[0]
	files, err := filepath.Glob(filepath.Join(dir, "*.go"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	sort.Strings(files)

	var code, tests strings.Builder
	pkg := ""
	for _, path := range files {
		name := filepath.Base(path)
		if skip[name] {
			continue
		}
		fset := token.NewFileSet()
		f, err := parser.ParseFile(fset, path, nil, parser.ParseComments)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		pkg = f.Name.Name
		isTest := strings.HasSuffix(name, "_test.go")
		lines := fileLines(fset, f, isTest)
		if len(lines) == 0 {
			continue
		}
		out := &code
		if isTest {
			out = &tests
		}
		fmt.Fprintf(out, "%s:\n", name)
		for _, l := range lines {
			fmt.Fprintf(out, "  %s\n", l)
		}
	}
	fmt.Printf("## Package %s API (generated)\n\n", pkg)
	fmt.Print("These declarations already exist. Use them; do not redeclare them.\n\n")
	fmt.Print(code.String())
	if tests.Len() > 0 {
		fmt.Print("\nTest helpers (in _test.go files):\n")
		fmt.Print(tests.String())
	}
}

func fileLines(fset *token.FileSet, f *ast.File, isTest bool) []string {
	var out []string
	for _, d := range f.Decls {
		switch d := d.(type) {
		case *ast.FuncDecl:
			// In test files, Test functions are not useful API; helpers are.
			if isTest && strings.HasPrefix(d.Name.Name, "Test") {
				continue
			}
			sig := "func " + recv(fset, d) + d.Name.Name + strings.TrimPrefix(node(fset, d.Type), "func")
			out = append(out, withDoc(sig, d.Doc))
		case *ast.GenDecl:
			if isTest || d.Tok == token.IMPORT {
				continue
			}
			for _, s := range d.Specs {
				switch s := s.(type) {
				case *ast.TypeSpec:
					doc := s.Doc
					if doc == nil {
						doc = d.Doc
					}
					out = append(out, withDoc("type "+s.Name.Name+" "+typeExpr(fset, s.Type), doc))
				case *ast.ValueSpec:
					kw := "var"
					if d.Tok == token.CONST {
						kw = "const"
					}
					names := make([]string, len(s.Names))
					for i, n := range s.Names {
						names[i] = n.Name
					}
					line := kw + " " + strings.Join(names, ", ")
					if len(s.Values) == len(s.Names) && len(s.Names) == 1 {
						line += " = " + node(fset, s.Values[0])
					}
					out = append(out, line)
				}
			}
		}
	}
	return out
}

// typeExpr prints struct types on one line with exported fields only, since
// unexported fields (mutexes, maps) are not part of how callers use a type.
func typeExpr(fset *token.FileSet, t ast.Expr) string {
	st, ok := t.(*ast.StructType)
	if !ok {
		return node(fset, t)
	}
	var fields []string
	for _, fl := range st.Fields.List {
		var names []string
		for _, n := range fl.Names {
			if ast.IsExported(n.Name) {
				names = append(names, n.Name)
			}
		}
		if len(names) == 0 {
			continue
		}
		fields = append(fields, strings.Join(names, ", ")+" "+node(fset, fl.Type))
	}
	if len(fields) == 0 {
		return "struct{ /* unexported fields */ }"
	}
	return "struct{ " + strings.Join(fields, "; ") + " }"
}

func recv(fset *token.FileSet, f *ast.FuncDecl) string {
	if f.Recv == nil || len(f.Recv.List) == 0 {
		return ""
	}
	r := f.Recv.List[0]
	name := ""
	if len(r.Names) > 0 {
		name = r.Names[0].Name + " "
	}
	return "(" + name + node(fset, r.Type) + ") "
}

func withDoc(line string, doc *ast.CommentGroup) string {
	if doc == nil {
		return line
	}
	first := strings.TrimSpace(strings.SplitN(doc.Text(), "\n", 2)[0])
	if first == "" {
		return line
	}
	return line + "  // " + first
}

func node(fset *token.FileSet, n ast.Node) string {
	var buf bytes.Buffer
	printer.Fprint(&buf, fset, n)
	return strings.Join(strings.Fields(buf.String()), " ")
}
