/**
 * Moteur Cartographique AROME HD — Rendu Raster Continu & Fond Satellite
 */
class LeafletWeatherEngine {
    constructor(mapContainerId, options = {}) {
        this.containerId = mapContainerId;
        this.currentLayer = options.layer || 'temperature';
        this.currentModel = options.model || 'arome';
        this.currentTheme = options.theme || 'standard';
        this.currentRegionKey = 'france';
        this.currentStep = 0;
        this.manifest = window.WeatherManifest || null;
        this.weatherOverlay = null;

        // Fonds de cartes
        this.baseLayers = {
            satellite: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?v=3', {
                attribution: '&copy; ESRI World Imagery',
                maxZoom: 19,
                crossOrigin: true
            }),
            dark: L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; CartoDB &copy; OpenStreetMap',
                maxZoom: 18
            }),
            topo: L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenTopoMap',
                maxZoom: 17
            })
        };

        // Carte Leaflet
        this.map = L.map(this.containerId, {
            center: [46.5, 2.5],
            zoom: 6,
            zoomControl: false,
            layers: [this.baseLayers.satellite]
        });

        // Contours départementaux fluorescents
        this.departementsLayer = L.geoJSON(null, {
            style: {
                color: '#00d2ff',
                weight: 1.4,
                opacity: 0.85,
                fillOpacity: 0
            }
        }).addTo(this.map);

        // Groupe de calques pour les villes d'Europe 1
        this.citiesLayer = L.layerGroup().addTo(this.map);

        // Chargement du découpage départemental officiel
        fetch('https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements.geojson')
            .then(r => r.json())
            .then(data => {
                if (data) this.departementsLayer.addData(data);
            })
            .catch(() => {});

        this.onProbeUpdate = options.onProbeUpdate || null;
        this.onPointClick = options.onPointClick || null;
        this.onManifestLoaded = options.onManifestLoaded || null;

        this.bindEvents();
    }

    setBasemap(basemapKey) {
        Object.values(this.baseLayers).forEach(layer => this.map.removeLayer(layer));
        if (this.baseLayers[basemapKey]) {
            this.baseLayers[basemapKey].addTo(this.map);
            this.baseLayers[basemapKey].bringToBack();
        }
    }

    init() {
        if (this.manifest && this.onManifestLoaded) {
            this.onManifestLoaded(this.manifest);
        }
        this.loadStep(0);
        this.updateCityMarkers('france');
    }

    loadStep(stepIndex) {
        if (!this.manifest || !this.manifest.steps) return;
        this.currentStep = Math.max(0, Math.min(this.manifest.steps.length - 1, stepIndex));
        const step = this.manifest.steps[this.currentStep];
        if (!step) return;

        let imageRelPath = step.files && step.files[this.currentLayer];
        if (!imageRelPath) {
            imageRelPath = `output/maps/${this.currentLayer}/${String(this.currentStep).padStart(3, '0')}.webp`;
        }

        const b = this.manifest.bounds || { south: 41.0, west: -5.5, north: 51.5, east: 10.0 };
        const imageBounds = [[b.south, b.west], [b.north, b.east]];

        if (this.weatherOverlay) {
            this.map.removeLayer(this.weatherOverlay);
        }

        // Calque météo continu haute définition
        const opacity = this.currentLayer === 'pluie_1h' ? 0.88 : 0.78;
        this.weatherOverlay = L.imageOverlay(imageRelPath, imageBounds, {
            opacity: opacity,
            interactive: false
        }).addTo(this.map);

        this.weatherOverlay.bringToFront();
        this.departementsLayer.bringToFront();
        this.citiesLayer.bringToFront();
    }

    updateCityMarkers(regionKey) {
        this.citiesLayer.clearLayers();
        const regions = window.Europe1Regions || {};
        const regConfig = regions[regionKey] || regions['france'];
        if (!regConfig || !regConfig.cities) return;

        regConfig.cities.forEach(city => {
            const cityName = city.name.toUpperCase();
            const iconHtml = `
                <div class="city-marker-badge">
                    <span class="city-dot"></span>
                    <span class="city-name-text">${cityName}</span>
                </div>
            `;

            const customIcon = L.divIcon({
                className: 'custom-city-divicon',
                html: iconHtml,
                iconSize: [110, 26],
                iconAnchor: [55, 13]
            });

            const marker = L.marker([city.lat, city.lon], { icon: customIcon, interactive: true });
            marker.on('click', () => {
                if (this.onPointClick) {
                    this.onPointClick({ lat: city.lat, lon: city.lon, cityName: city.name });
                }
            });
            this.citiesLayer.addLayer(marker);
        });

        this.citiesLayer.bringToFront();
    }

    setLayer(layerKey) {
        this.currentLayer = layerKey;
        this.loadStep(this.currentStep);
    }

    setTheme(themeKey) {
        this.currentTheme = themeKey;
        this.loadStep(this.currentStep);
    }

    setRegion(regionKey) {
        this.currentRegionKey = regionKey;
        const regions = window.Europe1Regions || {};
        const reg = regions[regionKey] || regions['france'];
        if (!reg) return;

        if (reg.center && reg.zoom) {
            this.map.flyTo(reg.center, reg.zoom, { duration: 0.8 });
        } else if (reg.center) {
            this.map.flyTo(reg.center, 8, { duration: 0.8 });
        }

        this.updateCityMarkers(regionKey);
    }

    bindEvents() {
        this.map.on('mousemove', (e) => {
            if (this.onProbeUpdate) {
                this.onProbeUpdate({
                    lat: e.latlng.lat,
                    lon: e.latlng.lng,
                    containerPoint: e.containerPoint
                });
            }
        });

        this.map.on('click', (e) => {
            if (this.onPointClick) {
                this.onPointClick({
                    lat: e.latlng.lat,
                    lon: e.latlng.lng
                });
            }
        });
    }
}

window.LeafletWeatherEngine = LeafletWeatherEngine;
