import unittest

from editor.exporter import (
    haversine_m,
    merge_road_vertices,
    refinery_export,
    to_roads_geojson,
    to_stations_geojson,
    validate_traffic_lights,
)
from editor.models import (
    Project,
    Refinery,
    RoadFeature,
    StationFeature,
    TrafficLightMarker,
)


def make_project(**kwargs: object) -> Project:
    defaults: dict[str, object] = {
        "roads": [],
        "stations": [],
        "refinery": None,
        "traffic_lights": [],
    }
    defaults.update(kwargs)
    return Project(**defaults)  # type: ignore[arg-type]


class HaversineTests(unittest.TestCase):
    def test_zero_distance(self) -> None:
        self.assertAlmostEqual(haversine_m(56.0, 47.0, 56.0, 47.0), 0.0, places=6)

    def test_known_short_distance(self) -> None:
        # ~111m per 0.001 degree of latitude.
        dist = haversine_m(56.0, 47.0, 56.001, 47.0)
        self.assertGreater(dist, 100)
        self.assertLess(dist, 115)


class RoadsGeoJsonTests(unittest.TestCase):
    def test_basic_shape_matches_map_import_service_expectations(self) -> None:
        project = make_project(
            roads=[
                RoadFeature(
                    id="r1",
                    road_type="trunk",
                    max_speed_kmh=90,
                    oneway=True,
                    coordinates=[(47.95, 56.70), (47.96, 56.71)],
                )
            ]
        )
        geojson = to_roads_geojson(project)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 1)
        feature = geojson["features"][0]
        self.assertEqual(feature["type"], "Feature")
        self.assertEqual(feature["geometry"]["type"], "LineString")
        self.assertEqual(feature["properties"]["road_type"], "trunk")
        self.assertEqual(feature["properties"]["max_speed_kmh"], 90)
        self.assertTrue(feature["properties"]["oneway"])
        # coordinates must be [lon, lat] pairs, matching GeoJSON / the parser.
        self.assertEqual(feature["geometry"]["coordinates"][0], [47.95, 56.70])

    def test_two_roads_drawn_almost_touching_merge_into_shared_node(self) -> None:
        # Two lines whose endpoints are 1-2 meters apart (typical hand-drawing
        # imprecision) must collapse to the exact same coordinate so the
        # backend's round-to-6-decimals node dedup treats them as one node.
        project = make_project(
            roads=[
                RoadFeature(
                    id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9000, 56.6000), (47.9100, 56.6000)],
                ),
                RoadFeature(
                    id="r2", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9100005, 56.6000006), (47.9200, 56.6000)],
                ),
            ]
        )
        geojson = to_roads_geojson(project)
        end_of_r1 = tuple(geojson["features"][0]["geometry"]["coordinates"][-1])
        start_of_r2 = tuple(geojson["features"][1]["geometry"]["coordinates"][0])
        self.assertEqual(end_of_r1, start_of_r2)

    def test_far_apart_endpoints_stay_distinct(self) -> None:
        project = make_project(
            roads=[
                RoadFeature(
                    id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9000, 56.6000), (47.9500, 56.6000)],
                ),
                RoadFeature(
                    id="r2", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9600, 56.6000), (47.9700, 56.6000)],
                ),
            ]
        )
        geojson = to_roads_geojson(project)
        end_of_r1 = tuple(geojson["features"][0]["geometry"]["coordinates"][-1])
        start_of_r2 = tuple(geojson["features"][1]["geometry"]["coordinates"][0])
        self.assertNotEqual(end_of_r1, start_of_r2)

    def test_degenerate_road_after_snapping_is_dropped(self) -> None:
        # Both endpoints snap onto the same existing node -> zero-length road.
        project = make_project(
            roads=[
                RoadFeature(
                    id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9000, 56.6000), (47.9500, 56.6000)],
                ),
                RoadFeature(
                    id="r2", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9000001, 56.6000001), (47.9000002, 56.6000002)],
                ),
            ]
        )
        geojson = to_roads_geojson(project)
        self.assertEqual(len(geojson["features"]), 1)


class StationsGeoJsonTests(unittest.TestCase):
    def test_price_converted_to_kopecks(self) -> None:
        project = make_project(
            stations=[
                StationFeature(
                    id="s1", osm_id="custom-1", name="АЗС №1",
                    base_price_rub=35000, settlement="Йошкар-Ола",
                    lon=47.8845, lat=56.6389,
                )
            ]
        )
        geojson = to_stations_geojson(project)
        feature = geojson["features"][0]
        self.assertEqual(feature["properties"]["base_price"], 3500000)
        self.assertEqual(feature["properties"]["osm_id"], "custom-1")
        self.assertEqual(feature["geometry"]["coordinates"], [47.8845, 56.6389])


class RefineryExportTests(unittest.TestCase):
    def test_none_when_unset(self) -> None:
        self.assertIsNone(refinery_export(make_project()))

    def test_snippet_contains_constants(self) -> None:
        project = make_project(refinery=Refinery(name="Нефтебаза Тест", lon=47.9, lat=56.7))
        data = refinery_export(project)
        assert data is not None
        self.assertIn("REFINERY_NAME", data["seed_game_data_snippet"])
        self.assertIn("REFINERY_LATITUDE = 56.7", data["seed_game_data_snippet"])


class TrafficLightValidationTests(unittest.TestCase):
    def test_three_way_intersection_is_ok(self) -> None:
        # A T-junction: three segments meeting at (47.90, 56.60).
        hub = (47.90, 56.60)
        project = make_project(
            roads=[
                RoadFeature(id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                            coordinates=[(47.89, 56.60), hub]),
                RoadFeature(id="r2", road_type="local", max_speed_kmh=50, oneway=False,
                            coordinates=[hub, (47.91, 56.60)]),
                RoadFeature(id="r3", road_type="local", max_speed_kmh=50, oneway=False,
                            coordinates=[hub, (47.90, 56.61)]),
            ],
            traffic_lights=[TrafficLightMarker(id="t1", lon=hub[0], lat=hub[1])],
        )
        checks = validate_traffic_lights(project)
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].degree, 3)

    def test_pass_through_point_is_not_ok(self) -> None:
        # Only two segments meet -> not a real intersection, no light.
        hub = (47.90, 56.60)
        project = make_project(
            roads=[
                RoadFeature(id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                            coordinates=[(47.89, 56.60), hub, (47.91, 56.60)]),
            ],
            traffic_lights=[TrafficLightMarker(id="t1", lon=hub[0], lat=hub[1])],
        )
        checks = validate_traffic_lights(project)
        self.assertFalse(checks[0].ok)
        self.assertEqual(checks[0].degree, 2)

    def test_light_far_from_any_road_is_flagged(self) -> None:
        project = make_project(
            roads=[
                RoadFeature(id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                            coordinates=[(47.89, 56.60), (47.91, 56.60)]),
            ],
            traffic_lights=[TrafficLightMarker(id="t1", lon=48.5, lat=57.5)],
        )
        checks = validate_traffic_lights(project)
        self.assertFalse(checks[0].ok)
        self.assertIsNone(checks[0].snapped_to)


class MergeRoadVerticesTests(unittest.TestCase):
    def test_neighbors_symmetric(self) -> None:
        project = make_project(
            roads=[
                RoadFeature(id="r1", road_type="local", max_speed_kmh=50, oneway=True,
                            coordinates=[(47.89, 56.60), (47.90, 56.60)]),
            ]
        )
        merge = merge_road_vertices(project)
        a, b = merge.merged_roads[0]
        self.assertIn(b, merge.neighbors[a])
        self.assertIn(a, merge.neighbors[b])  # oneway must not affect topology/degree


if __name__ == "__main__":
    unittest.main()
