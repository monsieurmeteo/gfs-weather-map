/**
 * Manifeste officiel pré-chargé pour fonctionnement 100% autonome et sans blocage CORS local
 */
const WeatherManifest = {
    schema_version: 6,
    status: "ok",
    bounds: {
        south: 41.0,
        west: -5.5,
        north: 51.5,
        east: 10.0
    },
    width: 1200,
    height: 900,
    layers: {
        temperature: { label: "Température à 2 m", unit: "°C", decimals: 1 },
        pluie_1h: { label: "Pluie horaire", unit: "mm/h", decimals: 1 },
        rafales: { label: "Rafales de vent", unit: "km/h", decimals: 0 },
        mucape: { label: "Instabilité orageuse", unit: "J/kg", decimals: 0 }
    },
    steps: Array.from({ length: 25 }, (_, i) => ({
        lead_hour: i,
        files: {
            temperature: `output/maps/temperature/${String(i).padStart(3, '0')}.webp`,
            pluie_1h: `output/maps/pluie_1h/${String(i).padStart(3, '0')}.webp`,
            rafales: `output/maps/rafales/${String(i).padStart(3, '0')}.webp`,
            mucape: `output/maps/mucape/${String(i).padStart(3, '0')}.webp`
        }
    }))
};

window.WeatherManifest = WeatherManifest;
