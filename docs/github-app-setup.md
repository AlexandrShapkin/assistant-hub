# GitHub App auth foundation (Issue #34)

Scope: an isolated authentication building block for a future private repository
read-only adapter, child of [#8](https://github.com/AlexandrShapkin/assistant-hub/issues/8).
Acceptance: deterministic fake signer/transport tests, strict repository and
permission confinement, private file checks, redacted objects, bounded requests,
and memory-only refresh/clear behavior. Validation uses the full Python suite,
compile checks, doctor, Node tests, public-tree hygiene and diff checks.

There is **no registered app, private reader, server binding or verified live
credential exchange** in this change. The public reader and public `web/` demo
are independent. There are no account actions, VPS changes, OAuth flows, private
API reads, background work or outgoing dispatch. The only implemented network
operation is an explicitly called installation-token POST; it has not been used
with credentials. Tests use synthetic tokens and a fake signer, without keys.

## Future owner setup (instructions only)

1. Review [creating a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app).
   Register an app under the intended owner only when ready for a separate live
   verification task. Record the numeric App ID. No OAuth/client secret is used
   by this module. Disable webhooks; this foundation has no webhook receiver.
2. Set repository permissions to **Issues: read-only**, **Pull requests:
   read-only**, **Actions: read-only**, and **Metadata: read-only** (GitHub's
   required metadata permission). Leave account, organization and all other
   optional permissions unset. No write permissions or contents access are needed.
   See [choosing permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).
3. Follow [installation instructions](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app).
   Choose **Only select repositories**, selecting only the intended repository.
   Record its `OWNER/REPO` and the installation ID. Do not select all repositories.
4. Separately decide key custody before generating or downloading any key. Use
   [GitHub's private-key guidance](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/managing-private-keys-for-github-apps).
   Keep an unencrypted RSA PEM key outside every Git working tree, in an existing
   owner-owned POSIX directory exactly 0700, file exactly 0600, single regular
   file link, no symlinks anywhere in its path. No automatic directory creation,
   permission repair, key generation or key download is provided.
5. A future trusted caller may construct `AppInstallation(app_id,
   installation_id, repository, absolute_private_key_path)` and explicitly inject
   `OpenSSLSigner(Path('/absolute/system/openssl'))` into
   `InstallationTokenManager`. The executable must be a trusted system binary;
   there is no PATH lookup, package installation or default key. Do not run an
   exchange merely to follow this document: live validation remains separate.

Open question: **where should the owner's private key live**, and who controls
backup, encrypted storage, rotation and incident recovery? No home-path default
or production vault has been selected. Do not place paths, keys or credentials
in repository configuration, browser storage, environment files or screenshots.

## API and fail-closed behavior

`build_app_jwt(config, signer, clock)` returns a redacted `AppJWT`; `.value` is
sensitive. The trusted callable `signer(config, signing_bytes)` returns bytes.
The injected clock returns Unix seconds. Claims are RS256, `iat=now-60`,
`exp=now+480`, numeric `iss=app_id`; compact segments have no padding. These
follow [GitHub JWT requirements](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app).
The optional OpenSSL signer recognizes unencrypted PKCS#1/PKCS#8 RSA PEM envelopes;
OpenSSL validates the actual key and signs. Fake signer tests establish byte
contracts, **not cryptographic verification or interoperability**.

`InstallationTokenManager.get_token()` returns a redacted `InstallationToken`
with sensitive `.value` and Unix `.expires_at`. Transport injection has signature
`transport(url, method, headers, body_bytes) -> (status, response_bytes)`; injected
code is trusted and must not log inputs. The default transport uses a fresh
stdlib HTTPS opener with certificate verification, no proxies, redirects,
cookies, retries or ambient authentication; timeout is eight seconds per socket
operation and response reading is bounded to 16 KiB plus one detection byte.
This is not an absolute wall-clock deadline across DNS/TLS/read operations.

The [installation access-token endpoint](https://docs.github.com/en/rest/apps/apps?apiVersion=2026-03-10#create-an-installation-access-token-for-an-app)
is fixed to `api.github.com/app/installations/{configured_id}/access_tokens`,
with API version `2026-03-10`. The POST always requests one repository name and
exactly the four read permissions above. Returned URLs are never used. Only 201
is accepted, with a bounded ASCII bearer value, aware ISO expiry more than 60
and at most 3700 seconds ahead, exactly the requested permission map, and exactly one repository with a case-insensitive ASCII match for the
configured `OWNER/REPO` identity (GitHub preserves display casing). Installation
tokens may use the newer dot-separated JWT-like representation introduced by
GitHub in 2026; token length and format are not assumed to remain 40 characters.

**GitHub may vary response field shapes or omit repository/permission details.**
This implementation rejects missing details, extra read permissions as well as
write permissions, extra repositories, duplicate JSON keys and malformed data.
No fallback listing endpoint or broad token is accepted. Official API examples
are not evidence that this exact exchange works for a real installation; a future
explicitly authorized interoperability task must assess those shapes first.

Each manager is bound to one immutable app/installation/repository selection.
A lock serializes issuance, refresh and clearing. Cached values are reused only
before `expires_at-90`; failures and clock rollback clear the cache. `clear()`
and its alias `revoke()` only forget the **local** token; they do not revoke it
at GitHub. Previously returned references may remain valid until GitHub expiry.
Remote revocation, key rotation and distributed cache coordination are not
implemented. Python cannot guarantee secret memory erasure. Never log values,
request headers, provider responses or subprocess diagnostics.
