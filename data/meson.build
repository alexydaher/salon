schemas_dir = get_option('datadir') / 'glib-2.0' / 'schemas'

install_data(
  'io.github.alexydaher.Salon.gschema.xml',
  install_dir: schemas_dir,
)

# Compiles gschemas.compiled into the build dir so the app can run
# uninstalled via GSETTINGS_SCHEMA_DIR (see the ./salon dev launcher).
# depend_files is load-bearing: without it Meson never notices the schema
# changed, and `meson compile` cheerfully reports "no work to do" while the
# app keeps reading the previous set of keys.
gnome.compile_schemas(
  build_by_default: true,
  depend_files: files('io.github.alexydaher.Salon.gschema.xml'),
)

desktop_conf = configuration_data()
desktop_conf.set('APP_ID', 'io.github.alexydaher.Salon')

configure_file(
  input: 'io.github.alexydaher.Salon.desktop.in',
  output: 'io.github.alexydaher.Salon.desktop',
  configuration: desktop_conf,
  install: true,
  install_dir: datadir / 'applications',
)

# The session entry (§6.11): picking "Salon" at the login screen starts
# gnome-session with a session definition whose required components are the
# Shell and Salon, rather than the full GNOME desktop with Salon on top.
session_conf = configuration_data()
session_conf.set('APP_ID', 'io.github.alexydaher.Salon')

configure_file(
  input: 'io.github.alexydaher.Salon.session.in',
  output: 'salon.session',
  configuration: session_conf,
  install: true,
  install_dir: datadir / 'gnome-session' / 'sessions',
)

configure_file(
  input: 'io.github.alexydaher.Salon.session.desktop.in',
  output: 'salon.desktop',
  configuration: session_conf,
  install: true,
  install_dir: datadir / 'wayland-sessions',
)

# AppStream metadata: what a software centre shows, and what Flathub
# requires before it will take a submission at all.
metainfo = configure_file(
  input: 'io.github.alexydaher.Salon.metainfo.xml.in',
  output: 'io.github.alexydaher.Salon.metainfo.xml',
  configuration: desktop_conf,
  install: true,
  install_dir: datadir / 'metainfo',
)

# Both files are validated as part of the build when the tools are present:
# a metainfo file with a typo in it fails at submission time otherwise, which
# is the worst moment to find out.
appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test(
    'validate-metainfo',
    appstreamcli,
    args: ['validate', '--no-net', '--explain', metainfo],
  )
endif

desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test(
    'validate-desktop-entry',
    desktop_file_validate,
    args: [meson.current_build_dir() / 'io.github.alexydaher.Salon.desktop'],
  )
endif

subdir('icons')
subdir('style')

install_subdir(
  'browser-extension',
  install_dir: pkgdatadir,
)

gnome.compile_resources(
  'salon',
  'salon.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  build_by_default: true,
  source_dir: [meson.current_source_dir(), meson.current_build_dir()],
  dependencies: [gen_tokens_css],
)
