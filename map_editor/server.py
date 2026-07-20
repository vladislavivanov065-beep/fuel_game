#!/usr/bin/env python3
"""Standalone local web server for the fuel_game map editor.

No third-party dependencies -- runs with the Python 3 standard library only.

Usage:
    python3 server.py [--port 8765]

Then open http://127.0.0.1:8765/ in a browser.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from editor import exporter, storage
from editor.models import Project, ProjectValidationError
from editor.storage import InvalidProjectNameError

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_PROJECT = "default"


class EditorRequestHandler(BaseHTTPRequestHandler):
    server_version = "MapEditor/1.0"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # keep the console quiet; errors still raise/print via default handlers

    # -- helpers ---------------------------------------------------------

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file_download(self, filename: str, content: dict[str, object] | str) -> None:
        if isinstance(content, str):
            body = content.encode("utf-8")
            content_type = "text/plain; charset=utf-8"
        else:
            body = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
            content_type = "application/geo+json; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _query_param(self, query: dict[str, list[str]], key: str, default: str) -> str:
        values = query.get(key)
        return values[0] if values else default

    # -- static files ------------------------------------------------

    def _serve_static(self, path: str) -> None:
        if path == "/" or path == "":
            path = "/index.html"
        path = path.removeprefix("/static/")
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR not in target.parents and target != STATIC_DIR:
            self.send_error(403, "Forbidden")
            return
        if not target.is_file():
            self.send_error(404, "Not found")
            return
        content_type, _ = mimetypes.guess_type(str(target))
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing -----------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        name = self._query_param(query, "name", DEFAULT_PROJECT)

        try:
            if parsed.path == "/api/project":
                project = storage.load_project(name)
                self._send_json(200, project.to_dict())
                return
            if parsed.path == "/api/projects":
                self._send_json(200, {"projects": storage.list_projects()})
                return
            if parsed.path == "/api/export/roads.geojson":
                project = storage.load_project(name)
                geojson = exporter.to_roads_geojson(project)
                self._send_file_download("mari_el_roads.geojson", geojson)
                return
            if parsed.path == "/api/export/stations.geojson":
                project = storage.load_project(name)
                geojson = exporter.to_stations_geojson(project)
                self._send_file_download("mari_el_stations.geojson", geojson)
                return
            if parsed.path == "/api/export/refinery":
                project = storage.load_project(name)
                data = exporter.refinery_export(project)
                if data is None:
                    self._send_json(404, {"error": "Refinery not set in this project"})
                    return
                self._send_file_download("refinery_seed_snippet.py", data["seed_game_data_snippet"])
                return
            if parsed.path == "/api/validate":
                project = storage.load_project(name)
                checks = exporter.validate_traffic_lights(project)
                self._send_json(
                    200,
                    {
                        "traffic_lights": [
                            {
                                "id": c.id,
                                "lon": c.lon,
                                "lat": c.lat,
                                "degree": c.degree,
                                "ok": c.ok,
                                "message": c.message,
                            }
                            for c in checks
                        ]
                    },
                )
                return
        except (InvalidProjectNameError, ProjectValidationError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        self._serve_static(parsed.path)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        name = self._query_param(query, "name", DEFAULT_PROJECT)

        if parsed.path != "/api/project":
            self.send_error(404, "Not found")
            return

        try:
            raw = self._read_json_body()
            project = Project.from_dict(raw)
            storage.save_project(name, project)
            self._send_json(200, {"saved": True, "name": name})
        except (InvalidProjectNameError, ProjectValidationError, KeyError, ValueError) as exc:
            self._send_json(400, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        name = self._query_param(query, "name", DEFAULT_PROJECT)

        if parsed.path != "/api/export/write":
            self.send_error(404, "Not found")
            return

        try:
            project = storage.load_project(name)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            roads_path = OUTPUT_DIR / "mari_el_roads.geojson"
            stations_path = OUTPUT_DIR / "mari_el_stations.geojson"
            roads_path.write_text(
                json.dumps(exporter.to_roads_geojson(project), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            stations_path.write_text(
                json.dumps(exporter.to_stations_geojson(project), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            written = [str(roads_path), str(stations_path)]

            refinery_data = exporter.refinery_export(project)
            if refinery_data is not None:
                refinery_path = OUTPUT_DIR / "refinery_seed_snippet.py"
                refinery_path.write_text(refinery_data["seed_game_data_snippet"], encoding="utf-8")
                written.append(str(refinery_path))

            checks = exporter.validate_traffic_lights(project)
            self._send_json(
                200,
                {
                    "written": written,
                    "traffic_light_warnings": [
                        {"id": c.id, "message": c.message} for c in checks if not c.ok
                    ],
                },
            )
        except (InvalidProjectNameError, ProjectValidationError) as exc:
            self._send_json(400, {"error": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fuel_game map editor")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), EditorRequestHandler)
    print(f"Map editor running at http://{args.host}:{args.port}/")
    print(f"Projects saved under: {storage.PROJECTS_DIR}")
    print(f"Exports written under: {OUTPUT_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
