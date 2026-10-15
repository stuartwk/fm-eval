## Codebase conventions
- Read path parameters with r.PathValue("id") (Go 1.22+ net/http routing). Never parse r.URL.Path.
- Every new handler must be registered with mux.HandleFunc in its resource's routes method.
- Store Get methods return (value, ok bool): check ok, not an error.
