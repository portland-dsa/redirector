from enum import StrEnum

import che_deploya
from che_deploya import (
    Component,
    DeploySpec,
    Environment,
    Secret,
    SharedRestart,
    Stages,
    StaticUnit,
    TemplatedUnit,
)


class ServiceEnv(StrEnum):
    """The two domains rendered into the unit as `Environment=` lines.

    Each member's value is both its key in the encrypted secrets file and the
    `${...}` placeholder it fills in the unit template.
    """

    #: Our own domain. Branches CNAME their names to `redirect.<host>`.
    Host = "host"
    #: The branch's domain. Only it and the names beneath it are served.
    Target = "target"


REDIRECTOR = DeploySpec(
    root="redirector",
    package="redirector_deploy",
    # One instance: there is no staging redirector.
    stages=frozenset({Stages.Production}),
    components=[
        Component(
            name="service",
            # No credentials - the file holds only the two domains the unit renders.
            # It is still declared as the component's Secret because that is what
            # bundles it into the archive and stages it on the box; an Environment
            # with its own src gets neither.
            secrets=Secret(
                names=frozenset(), src="{repo_root}/secrets/domains.enc.yml"
            ),
            units=[
                TemplatedUnit(
                    src="{repo_root}/deploy/redirector.service.tmpl",
                    resource_loc="assets/redirector.service",
                    dest="/etc/systemd/system/redirector.service",
                    env=Environment(names=frozenset(ServiceEnv)),
                ),
            ],
            # No restart on purpose: activation restarts the service through the
            # deploy wrapper, and a fresh box has no release to start yet.
        ),
        Component(
            name="ingress",
            # The catch-all site and its ask gate install together, ahead of the one
            # restart: Caddy refuses to start with an on-demand site and no gate. Both
            # files share a basename, so each names its own resource_loc to keep them
            # apart in the bundle. Neither is a whole Caddyfile on its own, so there
            # is no check here; rosadmin's ingress owns the root that imports them.
            units=[
                StaticUnit(
                    src="{repo_root}/deploy/caddy/global/redirector.caddy",
                    resource_loc="assets/global/redirector.caddy",
                    dest="/etc/caddy/global/redirector.caddy",
                ),
                StaticUnit(
                    src="{repo_root}/deploy/caddy/sites/redirector.caddy",
                    resource_loc="assets/sites/redirector.caddy",
                    dest="/etc/caddy/sites/redirector.caddy",
                ),
            ],
            # admin off means restart is the only reload path.
            restart=SharedRestart("caddy.service"),
        ),
    ],
)

main = che_deploya.build_cli(REDIRECTOR)
