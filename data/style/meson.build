# tokens.css is generated from salon/core/tokens.py, the single source of
# truth for the design system. Never hand-edit the generated file.
gen_tokens_css = custom_target(
  'tokens.css',
  output: 'tokens.css',
  command: [
    py_installation,
    meson.project_source_root() / 'build-aux' / 'gen-tokens-css.py',
    '@OUTPUT@',
  ],
  build_by_default: true,
)
