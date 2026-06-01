"""zen: an everything-is-a-type compiler.

Module map:
    ast      AST dataclasses + enums
    types    the trie + fits() pointer lattice + infer()   (the one type space)
    lower    transcribe/erase types to C
    parser   tree-sitter front end (parse -> ast)
    main     CLI driver + build.zen interpreter
"""
