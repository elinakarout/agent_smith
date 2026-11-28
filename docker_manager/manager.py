import docker
from docker.models.containers import Container
from typing import Optional


class DockerManager:
    def __init__(
        self,
        image: str,
        working_dir: str = "/testbed",
        memory_limit: str = "4g",
    ):
        self.client = docker.from_env()
        self.image = image
        self.working_dir = working_dir
        self.memory_limit = memory_limit
        self.container: Optional[Container] = None

    def pull_image(self):
        try:
            self.client.images.get(self.image)
            return
        except docker.errors.ImageNotFound:
            pass
        print(f"Pulling image: {self.image}", file=sys.stderr, flush=True)
        self.client.images.pull(self.image)

    def start(self):
        if self.container is not None:
            raise RuntimeError("Container already started")

        self.container = self.client.containers.run(
            image=self.image,
            entrypoint=["/bin/sh", "-lc"],
            command=["while true; do sleep 3600; done"],
            detach=True,
            working_dir=self.working_dir,
            mem_limit=self.memory_limit,
            network_mode="none",
            labels={"agent-smith": "swebench"},
        )

        self.container.reload()

        if self.container.status != "running":
            raise RuntimeError("Container failed to start")

        return self.container

    def stop(self):
        if self.container is None:
            return
        container, self.container = self.container, None
        try:
            container.remove(force=True, v=True)  # force kills immediately, no 5s wait
        except docker.errors.NotFound:
            pass

    def __enter__(self):
        self.pull_image()
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
        return False