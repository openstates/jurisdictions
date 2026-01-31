"""
Dictionaries representing file mappings for initial data migration.
"""

ocdid_master_mapper = {'id': "id",
                        'name': "display_name",
                        'sameAs': "also_known_as",
                        'sameAsNote': "metadata.also_known_as_note",
                        'validThrough': "valid_asof",
                        'census_geoid': "geometries.government_identifiers.geoid",
                        'census_geoid_12': "geometries.government_identifiers.geoid_12",
                        'census_geoid_14': "geometries.government_identifiers.geoid_14",
                        'openstates_district': "metadata.openstates_district",
                        'placeholder_id': "metadata.placeholder_id", # Only 5284 values
                        'sch_dist_stateid': "metadata.sch_dist_stateid", # 15438 values
                        'state_id': "geometries.government_identifiers.stusps", # IS IT STATE CODE?
                        'validFrom': "valid_thru"
}
