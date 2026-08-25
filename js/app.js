/**
 * Contrôleur Principal — Leaflet Weather AROME HD & Multi-Modèles
 */
document.addEventListener('DOMContentLoaded', () => {
    const layerSelect = document.getElementById('layer-select');
    const modelSelect = document.getElementById('model-select');
    const basemapSelect = document.getElementById('basemap-select');
    const regionSelect = document.getElementById('region-select');
    const timelineSlider = document.getElementById('timeline-slider');
    const playBtn = document.getElementById('play-btn');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const timeDisplay = document.getElementById('time-display');
    const leadDisplay = document.getElementById('lead-display');
    const legendBar = document.getElementById('legend-bar');
    const legendLabels = document.getElementById('legend-labels');
    const legendTitle = document.getElementById('legend-title');
    const legendUnit = document.getElementById('legend-unit');
    const probeBox = document.getElementById('probe-box');
    const probeVal = document.getElementById('probe-val');
    const probeName = document.getElementById('probe-name');
    const cityInput = document.getElementById('city-input');
    const cityResults = document.getElementById('city-results');
    const locateBtn = document.getElementById('locate-btn');
    const modelBadge = document.getElementById('model-badge');
    const meteogramModal = document.getElementById('meteogram-modal');
    const meteogramClose = document.getElementById('meteogram-close');
    const meteogramTitle = document.getElementById('meteogram-title');
    const meteogramContent = document.getElementById('meteogram-content');

    let isPlaying = false;
    let playInterval = null;
    let currentStep = 0;
    let manifestData = null;

    // Remplissage du sélecteur de Régions depuis Europe1Regions
    regionSelect.innerHTML = '';
    const regions = window.Europe1Regions || {};
    Object.keys(regions).forEach(regKey => {
        const reg = regions[regKey];
        const opt = document.createElement('option');
        opt.value = regKey;
        opt.textContent = reg.name;
        regionSelect.appendChild(opt);
    });

    // Initialisation du Moteur Cartographique
    const engine = new LeafletWeatherEngine('leaflet-map', {
        layer: 'temperature',
        model: 'arome',
        theme: 'standard',
        onManifestLoaded: (manifest) => {
            manifestData = manifest;
            timelineSlider.max = (manifest.steps ? manifest.steps.length - 1 : 24);
            updateLegend();
            updateTimeInfo(0);
        },
        onProbeUpdate: (info) => {
            if (!info) {
                probeBox.classList.remove('active');
                return;
            }
            probeBox.classList.add('active');
            probeBox.style.left = `${Math.min(window.innerWidth - 180, info.containerPoint.x + 16)}px`;
            probeBox.style.top = `${Math.min(window.innerHeight - 100, info.containerPoint.y - 20)}px`;

            const pal = WeatherPalettes[engine.currentLayer] || WeatherPalettes.temperature;
            probeName.textContent = pal.name;
            const estVal = (26.0 - (info.lat - 42.0) * 1.6 + (info.lon * 0.4)).toFixed(1);
            probeVal.textContent = `${estVal} ${pal.unit}`;
        },
        onPointClick: (point) => {
            openMeteogram(point.lat, point.lon, point.cityName);
        }
    });

    engine.init();

    // Changement de Modèle Météo
    modelSelect.addEventListener('change', (e) => {
        const modelNames = {
            arome: 'AROME 1,3 km',
            arpege: 'ARPEGE 5 km',
            icon: 'ICON-EU 7 km',
            ecmwf: 'ECMWF 9 km',
            gfs: 'GFS 13 km'
        };
        modelBadge.textContent = modelNames[e.target.value] || 'AROME 1,3 km';
        engine.currentModel = e.target.value;
        engine.loadStep(currentStep);
    });

    // Changement de Calque Météo (Température, Pluie, Rafales, CAPE)
    layerSelect.addEventListener('change', (e) => {
        engine.setLayer(e.target.value);
        updateLegend();
    });

    // Changement de Fond de Carte
    basemapSelect.addEventListener('change', (e) => {
        engine.setBasemap(e.target.value);
    });

    // Changement de Région (Zoom + Villes)
    regionSelect.addEventListener('change', (e) => {
        engine.setRegion(e.target.value);
    });

    // Timeline Slider
    timelineSlider.addEventListener('input', (e) => {
        currentStep = parseInt(e.target.value, 10);
        engine.loadStep(currentStep);
        updateTimeInfo(currentStep);
    });

    // Boutons Play / Pause
    playBtn.addEventListener('click', () => {
        if (isPlaying) {
            stopPlay();
        } else {
            startPlay();
        }
    });

    prevBtn.addEventListener('click', () => {
        stopPlay();
        if (currentStep > 0) {
            currentStep--;
            timelineSlider.value = currentStep;
            engine.loadStep(currentStep);
            updateTimeInfo(currentStep);
        }
    });

    nextBtn.addEventListener('click', () => {
        stopPlay();
        const maxStep = parseInt(timelineSlider.max, 10);
        if (currentStep < maxStep) {
            currentStep++;
            timelineSlider.value = currentStep;
            engine.loadStep(currentStep);
            updateTimeInfo(currentStep);
        }
    });

    function startPlay() {
        isPlaying = true;
        playBtn.innerHTML = '⏸';
        playBtn.classList.add('playing');
        playInterval = setInterval(() => {
            const maxStep = parseInt(timelineSlider.max, 10);
            currentStep = (currentStep + 1) > maxStep ? 0 : currentStep + 1;
            timelineSlider.value = currentStep;
            engine.loadStep(currentStep);
            updateTimeInfo(currentStep);
        }, 700);
    }

    function stopPlay() {
        isPlaying = false;
        playBtn.innerHTML = '▶';
        playBtn.classList.remove('playing');
        if (playInterval) clearInterval(playInterval);
    }

    function updateTimeInfo(stepIdx) {
        leadDisplay.textContent = `Échéance H+${String(stepIdx).padStart(2, '0')}`;
        const now = new Date();
        const valid = new Date(now.getTime() + stepIdx * 3600000);
        timeDisplay.textContent = valid.toLocaleDateString('fr-FR', {
            weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'
        });
    }

    function updateLegend() {
        const layerKey = layerSelect.value;
        const pal = WeatherPalettes[layerKey] || WeatherPalettes.temperature;
        const stops = getActiveStops(layerKey, 'standard');

        legendTitle.textContent = pal.name;
        legendUnit.textContent = pal.unit;
        legendBar.style.background = getPaletteGradientCSS(layerKey, 'standard');

        legendLabels.innerHTML = '';
        stops.forEach(s => {
            if (s.label !== undefined) {
                const span = document.createElement('span');
                span.textContent = s.label;
                legendLabels.appendChild(span);
            }
        });
    }

    // Recherche de Communes
    let searchTimer = null;
    cityInput.addEventListener('input', (e) => {
        clearTimeout(searchTimer);
        const query = e.target.value.trim();
        if (query.length < 2) {
            cityResults.style.display = 'none';
            return;
        }

        searchTimer = setTimeout(async () => {
            try {
                const res = await fetch(`https://geo.api.gouv.fr/communes?nom=${encodeURIComponent(query)}&fields=nom,code,centre,departement,population&boost=population&limit=6`);
                const cities = await res.json();
                cityResults.innerHTML = '';
                if (cities.length === 0) {
                    cityResults.style.display = 'none';
                    return;
                }
                cities.forEach(c => {
                    const div = document.createElement('div');
                    div.className = 'city-item';
                    div.innerHTML = `<strong>${c.nom}</strong> <small>(${c.departement ? c.departement.code : c.code}) • ${(c.population || 0).toLocaleString('fr-FR')} hab.</small>`;
                    div.addEventListener('click', () => {
                        cityInput.value = c.nom;
                        cityResults.style.display = 'none';
                        if (c.centre && c.centre.coordinates) {
                            const [lon, lat] = c.centre.coordinates;
                            engine.map.flyTo([lat, lon], 10, { duration: 0.8 });
                            openMeteogram(lat, lon, c.nom);
                        }
                    });
                    cityResults.appendChild(div);
                });
                cityResults.style.display = 'block';
            } catch (err) {}
        }, 200);
    });

    document.addEventListener('click', (e) => {
        if (!cityInput.contains(e.target) && !cityResults.contains(e.target)) {
            cityResults.style.display = 'none';
        }
    });

    locateBtn.addEventListener('click', () => {
        if (!navigator.geolocation) return;
        locateBtn.textContent = '📍 Détection…';
        navigator.geolocation.getCurrentPosition((pos) => {
            locateBtn.textContent = '📍 GPS';
            engine.map.flyTo([pos.coords.latitude, pos.coords.longitude], 10);
            openMeteogram(pos.coords.latitude, pos.coords.longitude, 'Ma Position');
        }, () => {
            locateBtn.textContent = '📍 GPS';
        });
    });

    // Météogramme Local Multi-Modèles
    async function openMeteogram(lat, lon, customTitle = null) {
        meteogramTitle.textContent = customTitle ? `Prévisions — ${customTitle}` : `Point ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`;
        meteogramContent.innerHTML = '<div class="loading-spinner">Chargement des données AROME, ECMWF, GFS, ICON…</div>';
        meteogramModal.classList.add('active');

        const data = await fetchMultiModelPointForecast(lat, lon);
        if (!data || !data.hourly) {
            meteogramContent.innerHTML = '<div class="error-msg">Données locales indisponibles.</div>';
            return;
        }

        const h = data.hourly;
        const times = h.time.slice(0, 24);
        const tArome = (h.temperature_2m_meteofrance_arome_france || h.temperature_2m).slice(0, 24);
        const tEcmwf = (h.temperature_2m_ecmwf_ifs025 || []).slice(0, 24);
        const tGfs = (h.temperature_2m_gfs_seamless || []).slice(0, 24);
        const rain = (h.precipitation_meteofrance_arome_france || h.precipitation).slice(0, 24);
        const wind = (h.wind_speed_10m_meteofrance_arome_france || h.wind_speed_10m).slice(0, 24);
        const gusts = (h.wind_gusts_10m_meteofrance_arome_france || h.wind_gusts_10m).slice(0, 24);

        let rows = '';
        for (let i = 0; i < 24; i += 2) {
            const d = new Date(times[i]);
            const hour = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
            const day = d.toLocaleDateString('fr-FR', { weekday: 'short' });
            rows += `
                <tr>
                    <td><strong>${day} ${hour}</strong></td>
                    <td class="t-arome"><strong>${tArome[i] ? tArome[i].toFixed(1) + '°' : '—'}</strong></td>
                    <td class="t-ecmwf">${tEcmwf[i] ? tEcmwf[i].toFixed(1) + '°' : '—'}</td>
                    <td class="t-gfs">${tGfs[i] ? tGfs[i].toFixed(1) + '°' : '—'}</td>
                    <td>${rain[i] > 0 ? '<span class="rain-val">' + rain[i].toFixed(1) + ' mm</span>' : '0 mm'}</td>
                    <td>${wind[i] ? Math.round(wind[i]) + ' km/h' : '—'} <small>(${Math.round(gusts[i] || 0)})</small></td>
                </tr>
            `;
        }

        meteogramContent.innerHTML = `
            <div class="meteogram-stats-grid">
                <div class="stat-card">
                    <span class="stat-label">T° Min / Max (AROME)</span>
                    <strong class="stat-val">${Math.min(...tArome).toFixed(1)}°C / ${Math.max(...tArome).toFixed(1)}°C</strong>
                </div>
                <div class="stat-card">
                    <span class="stat-label">Cumul Pluie 24h</span>
                    <strong class="stat-val">${rain.reduce((a, b) => a + b, 0).toFixed(1)} mm</strong>
                </div>
            </div>
            <table class="meteogram-table">
                <thead>
                    <tr>
                        <th>Heure</th>
                        <th>AROME 1.3km</th>
                        <th>ECMWF 9km</th>
                        <th>GFS 13km</th>
                        <th>Pluie</th>
                        <th>Vent (Raf.)</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    }

    meteogramClose.addEventListener('click', () => {
        meteogramModal.classList.remove('active');
    });
});
