# Validation â€” 7 October 2026

- Read-only SSH inspection confirmed both reference hosts use Ubuntu 24.04 x86_64 and .NET/ASP.NET 6.0.36 containers; one runs six instances, the other one. No community configuration or addresses are included in this public project.
- Built the generic Docker image independently on an existing Linux host. The initial live Bullseye package URLs returned 404; switching to signed Debian archive indexes fixed the build. The resulting image reports both .NET and ASP.NET 6.0.36. Shell entrypoint syntax passes. With the game binary directory on `LD_LIBRARY_PATH`, all inspected native `.so` dependencies resolve.
- Six Python tests pass on Windows and Linux: valid example settings, invalid roots/duplicate ports/module names, isolated Compose output, ordinary module archive extraction and rejection of traversal/links/case collisions/backslash paths.
- No existing game container was restarted, changed or redeployed. Runtime image construction is separate from game provisioning.

Full fresh-VPS provisioning, Steam download through the new installer, authenticated mission startup, mod compatibility and player connectivity are not yet end-to-end verified. The implementation derives those steps from the existing operator setup and current official hosting documentation; do not interpret passing unit tests or an image build as proof of gameplay.
