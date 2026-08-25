python_sources = [
  '__init__.py',
  'window.py',
  'scale.py',
  'motion.py',
  'search.py',
  'osk.py',
  'qrcode.py',
  'keyboardpane.py',
  'home.py',
  'tile.py',
  'backdrop.py',
  'screensaver.py',
  'statusbar.py',
  'detailbar.py',
  'appsgrid.py',
  'overlays.py',
  'phonepairing.py',
  'remotehint.py',
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
