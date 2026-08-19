python_sources = [
  '__init__.py',
  'window.py',
  'scale.py',
  'motion.py',
  'search.py',
  'osk.py',
  'keyboardpane.py',
  'home.py',
  'tile.py',
  'backdrop.py',
  'statusbar.py',
  'appsgrid.py',
  'overlays.py',
  'osd.py',
  'textentry.py',
  'theme.py',
  'onboarding.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir / 'ui',
  )
endforeach

subdir('settings')
