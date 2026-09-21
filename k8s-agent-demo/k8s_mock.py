"""
A tiny, self-contained simulation of a Kubernetes cluster with ONE broken
Deployment, so the agent demo runs anywhere with zero infra.

The scenario (a very common real-world bug):
  The `web-api` Deployment sets env LOG_LEVEL="verbose".
  The app only accepts DEBUG|INFO|WARN|ERROR, so the container validates
  config at startup, prints a FATAL log line, and exits(1).
  Kubernetes restarts it, it crashes again -> CrashLoopBackOff.

The fix the agent must discover from the logs:
  set LOG_LEVEL to a valid value (e.g. INFO). Once patched, the pod
  is recreated and reports Running.
"""
from __future__ import annotations
import random
import string

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}


def _rand_suffix(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class MockCluster:
    def __init__(self) -> None:
        self.namespace = "default"
        self.deployment = "web-api"
        self.image = "web-api:1.4.2"
        self.replicas = 1
        # The bug lives here:
        self.env = {"PORT": "8080", "LOG_LEVEL": "verbose"}
        self.restart_count = 5
        self.pod = f"{self.deployment}-{_rand_suffix(9)}-{_rand_suffix(5)}"
        self.healthy = False  # recomputed from env
        self._recompute()

    # ---- internal ---------------------------------------------------------
    def _recompute(self) -> None:
        self.healthy = self.env.get("LOG_LEVEL", "") in VALID_LOG_LEVELS

    # ---- read tools -------------------------------------------------------
    def get_pods(self) -> str:
        if self.healthy:
            return (
                "NAME                          READY   STATUS    RESTARTS   AGE\n"
                f"{self.pod:<29} 1/1     Running   0          12s"
            )
        return (
            "NAME                          READY   STATUS             RESTARTS      AGE\n"
            f"{self.pod:<29} 0/1     CrashLoopBackOff   {self.restart_count} (20s ago)   4m17s"
        )

    def logs(self, pod: str) -> str:
        if self.healthy:
            return (
                "2026-09-21T18:11:02Z INFO  starting web-api v1.4.2\n"
                "2026-09-21T18:11:02Z INFO  config OK (LOG_LEVEL=INFO, PORT=8080)\n"
                "2026-09-21T18:11:02Z INFO  listening on :8080\n"
                "2026-09-21T18:11:02Z INFO  readiness probe passed"
            )
        return (
            "2026-09-21T18:02:11Z INFO  starting web-api v1.4.2\n"
            f'2026-09-21T18:02:11Z FATAL invalid LOG_LEVEL "{self.env.get("LOG_LEVEL")}" '
            "(allowed: DEBUG, INFO, WARN, ERROR)\n"
            "2026-09-21T18:02:11Z FATAL configuration validation failed, exiting (code 1)"
        )

    def describe_pod(self, pod: str) -> str:
        if self.healthy:
            state = (
                "    State:          Running\n"
                "      Started:      Mon, 21 Sep 2026 18:11:02 +0000\n"
                "    Ready:          True\n"
                "    Restart Count:  0"
            )
        else:
            state = (
                "    State:          Waiting\n"
                "      Reason:       CrashLoopBackOff\n"
                "    Last State:     Terminated\n"
                "      Reason:       Error\n"
                "      Exit Code:    1\n"
                f"    Restart Count:  {self.restart_count}"
            )
        return (
            f"Name:             {self.pod}\n"
            f"Namespace:        {self.namespace}\n"
            f"Controlled By:    ReplicaSet/{self.deployment}-{_rand_suffix(9)}\n"
            "Containers:\n"
            f"  {self.deployment}:\n"
            f"    Image:          {self.image}\n"
            "    Port:           8080/TCP\n"
            f"{state}\n"
            "    Environment:\n"
            + "".join(f"      {k}: {v}\n" for k, v in self.env.items())
        )

    def get_deployment_yaml(self, name: str) -> str:
        env_yaml = "\n".join(
            f"        - name: {k}\n          value: \"{v}\"" for k, v in self.env.items()
        )
        return (
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            f"  name: {self.deployment}\n"
            f"  namespace: {self.namespace}\n"
            "spec:\n"
            f"  replicas: {self.replicas}\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {self.deployment}\n"
            f"        image: {self.image}\n"
            "        ports:\n"
            "        - containerPort: 8080\n"
            "        env:\n"
            f"{env_yaml}"
        )

    # ---- write tool -------------------------------------------------------
    def set_env(self, name: str, key: str, value: str) -> str:
        old = self.env.get(key)
        self.env[key] = value
        self._recompute()
        if self.healthy:
            # Deployment rolls out a new pod
            self.pod = f"{self.deployment}-{_rand_suffix(9)}-{_rand_suffix(5)}"
            self.restart_count = 0
        return (
            f"deployment.apps/{self.deployment} env updated: "
            f"{key} {old!r} -> {value!r}\n"
            "deployment.apps/web-api restarted (rolling update)"
        )


# single shared instance for the process
cluster = MockCluster()
