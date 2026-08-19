python_sources = [
  '__init__.py',
  'appinfo.py',
  'artwork.py',
  'audio.py',
  'battery.py',
  'launcher.py',
  'pointer_injector.py',
  'pairing.py',
  'netinfo.py',
  'power.py',
  'screenlock.py',
  'cec_out.py',
]

foreach f : python_sources
  configure_file(
    input: f,
    output: f,
    copy: true,
    install: true,
    install_dir: moduledir / 'services',
  )
endforeach
