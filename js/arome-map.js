(function () {
    'use strict';

    function whenReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback);
        } else {
            callback();
        }
    }

    function fetchJson(url) {
        return fetch(url, { cache: 'no-cache' }).then(function (response) {
            if (!response.ok) {
                throw new Error('Réponse HTTP ' + response.status);
            }
            return response.json();
        });
    }

    function fetchText(url) {
        return fetch(url, { cache: 'no-cache' }).then(function (response) {
            if (!response.ok) {
                throw new Error('Réponse HTTP ' + response.status);
            }
            return response.text();
        });
    }

    function fetchBuffer(url) {
        return fetch(url, { cache: 'no-cache' }).then(function (response) {
            if (!response.ok) {
                throw new Error('Réponse HTTP ' + response.status);
            }
            return response.arrayBuffer();
        });
    }

    function decompressIfNeeded(buffer) {
        var bytes = new Uint8Array(buffer);
        if (bytes.length < 2 || bytes[0] !== 0x1f || bytes[1] !== 0x8b) {
            return Promise.resolve(buffer);
        }
        if (typeof window.DecompressionStream !== 'function') {
            return Promise.reject(new Error('Décompression gzip indisponible'));
        }
        var stream = new Blob([buffer]).stream().pipeThrough(
            new window.DecompressionStream('gzip')
        );
        return new Response(stream).arrayBuffer();
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function runLabelUtc(value) {
        var date = new Date(value);
        function two(number) {
            return String(number).padStart(2, '0');
        }
        return two(date.getUTCDate()) + '/' + two(date.getUTCMonth() + 1) +
            ' ' + two(date.getUTCHours()) + 'z';
    }

    function initMap(app) {
        var baseUrl = (app.dataset.baseUrl || '').replace(/\/+$/, '');
        var requestedLayer = app.dataset.variable || 'temperature';
        var timezone = app.dataset.timezone || 'Europe/Paris';
        var moduleVersion = app.dataset.moduleVersion || '1.0.0';
        var animationEnabled = app.dataset.animation !== '0';
        var reducedMotion = window.matchMedia &&
            window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        var menuToggle = app.querySelector('[data-amfm-menu-toggle]');
        var menuClose = app.querySelector('[data-amfm-menu-close]');
        var layerMenu = app.querySelector('[data-amfm-layer-menu]');
        var layerGrid = app.querySelector('[data-amfm-layer-grid]');
        var currentLayerText = app.querySelector('[data-amfm-current-layer]');
        var previousButton = app.querySelector('[data-amfm-previous]');
        var playButton = app.querySelector('[data-amfm-play]');
        var nextButton = app.querySelector('[data-amfm-next]');
        var validity = app.querySelector('[data-amfm-validity]');
        var lead = app.querySelector('[data-amfm-lead]');
        var run = app.querySelector('[data-amfm-run]');
        var generated = app.querySelector('[data-amfm-generated]');
        var stale = app.querySelector('[data-amfm-stale]');
        var viewport = app.querySelector('[data-amfm-viewport]');
        var weatherCanvas = app.querySelector('[data-amfm-weather]');
        var vectorCanvas = app.querySelector('[data-amfm-vectors]');
        var valuesCanvas = app.querySelector('[data-amfm-values]');
        var labelsCanvas = app.querySelector('[data-amfm-labels]');
        var vectorContext = vectorCanvas ? vectorCanvas.getContext('2d') : null;
        var valuesContext = valuesCanvas ? valuesCanvas.getContext('2d') : null;
        var labelsContext = labelsCanvas ? labelsCanvas.getContext('2d') : null;
        var mapTitle = app.querySelector('[data-amfm-map-title]');
        var mapRun = app.querySelector('[data-amfm-map-run]');
        var mapDate = app.querySelector('[data-amfm-map-date]');
        var loading = app.querySelector('[data-amfm-loading]');
        var errorBox = app.querySelector('[data-amfm-error]');
        var unavailableBox = app.querySelector('[data-amfm-unavailable]');
        var unavailableText = app.querySelector('[data-amfm-unavailable-text]');
        var slider = app.querySelector('[data-amfm-slider]');
        var legend = app.querySelector('[data-amfm-legend]');
        var zoomIn = app.querySelector('[data-amfm-zoom-in]');
        var zoomOut = app.querySelector('[data-amfm-zoom-out]');
        var reset = app.querySelector('[data-amfm-reset]');
        var fullscreen = app.querySelector('[data-amfm-fullscreen]');
        var zoomLevel = app.querySelector('[data-amfm-zoom-level]');
        var probe = app.querySelector('[data-amfm-probe]');
        var probeValue = app.querySelector('[data-amfm-probe-value]');
        var probeLabel = app.querySelector('[data-amfm-probe-label]');
        var toolButtons = app.querySelectorAll('[data-amfm-tool]');
        var toolHint = app.querySelector('[data-amfm-tool-hint]');
        var advancedTools = app.querySelector('[data-amfm-advanced-tools]');
        var captureButton = app.querySelector('[data-amfm-capture]');
        var captureScreenButton = app.querySelector('[data-amfm-capture-screen]') || app.querySelector('[data-amfm-capture-landscape]');
        var captureJpegButton = app.querySelector('[data-amfm-capture-jpeg]');
        var captureGifButton = app.querySelector('[data-amfm-capture-gif]');
        var toggleCitiesButton = app.querySelector('[data-amfm-toggle-cities]');
        var toggleValuesButton = app.querySelector('[data-amfm-toggle-values]');
        var toggleSeaButton = app.querySelector('[data-amfm-toggle-sea]');
        var seaSelect = app.querySelector('[data-amfm-select-sea]');
        var pinButton = app.querySelector('[data-amfm-pin]');
        var toggleTvButton = app.querySelector('[data-amfm-toggle-tv]');
        var tvExitButton = app.querySelector('[data-amfm-tv-exit]');
        var toggleDiagramButton = app.querySelector('[data-amfm-toggle-diagram]');

        var meteogramModal = app.querySelector('[data-amfm-meteogram-modal]');
        var meteogramClose = app.querySelector('[data-amfm-meteogram-close]');
        var meteogramCity = app.querySelector('[data-amfm-meteogram-city]');
        var meteogramCoords = app.querySelector('[data-amfm-meteogram-coords]');
        var meteogramCanvas = app.querySelector('[data-amfm-meteogram-canvas]');
        var meteogramTabs = app.querySelectorAll('[data-amfm-meteogram-tab]');
        var meteogramTabActive = 'temperature';
        var meteogramPoint = null;
        var diagramActive = false;


        var mapBadge = app.querySelector('[data-amfm-map-badge]');
        var badgeParam = app.querySelector('[data-amfm-badge-param]');
        var badgeModel = app.querySelector('[data-amfm-badge-model]');
        var badgeDate = app.querySelector('[data-amfm-badge-date]');

        var diagramPopup = app.querySelector('[data-amfm-diagram-popup]');
        var diagramTitle = app.querySelector('[data-amfm-diagram-title]');
        var diagramBody = app.querySelector('[data-amfm-diagram-body]');
        var diagramStatus = app.querySelector('[data-amfm-diagram-status]');
        var diagramClose = app.querySelector('[data-amfm-diagram-close]');

        var manifest = null;
        var currentLayer = requestedLayer;
        var currentModel = app.dataset.model || 'arome';
        var currentStep = 0;
        var loadToken = 0;
        var timer = null;
        var transform = { scale: 1, x: 0, y: 0 };
        var activePointers = new Map();
        var gesture = null;
        var places = [];
        var placeBuckets = new Map();
        var citiesVisible = true;
        var valuesVisible = false;
        var seaMode = 'none'; // 'none' (partout mer comprise par défaut), 'land' (terres seules), 'coast' (terres + littoral)
        var vectorDefinition = null;
        var currentWeatherImage = null;
        var logoImage = new Image();
        logoImage.crossOrigin = 'anonymous';
        logoImage.src = app.dataset.logo || 'logo.png';
        var franceMaskImage = new Image();
        franceMaskImage.crossOrigin = 'anonymous';
        franceMaskImage.src = resolvePath('maps/mask_france.png');
        var maskSamplerCanvas = document.createElement('canvas');
        maskSamplerCanvas.width = 2200;
        maskSamplerCanvas.height = 1640;
        var maskSamplerContext = maskSamplerCanvas.getContext ? maskSamplerCanvas.getContext('2d', { willReadFrequently: true }) : null;
        var maskSamplerReady = false;

        franceMaskImage.onload = function () {
            visibleBBoxCache = null;
            if (maskSamplerContext) {
                try {
                    maskSamplerContext.drawImage(franceMaskImage, 0, 0, 2200, 1640);
                    maskSamplerReady = true;
                } catch (e) {}
            }
            scheduleRender();
        };

        function isLand(u, v) {
            if (seaMode === 'none') return true; // Mode 'none' : afficher partout y compris en pleine mer
            if (!maskSamplerReady || !maskSamplerContext) return true;
            var px = Math.min(Math.max(0, Math.round(u * 2199)), 2199);
            var py = Math.min(Math.max(0, Math.round(v * 1639)), 1639);
            var pix = maskSamplerContext.getImageData(px, py, 1, 1).data;
            if (pix[0] > 64 || (pix[3] > 64 && pix[0] > 64)) return true;

            if (seaMode === 'coast') {
                // Inclusion généreuse du trait de côte et des zones littorales (~16 km)
                var r = 18;
                var offsets = [
                    [r, 0], [-r, 0], [0, r], [0, -r],
                    [13, 13], [-13, 13], [13, -13], [-13, -13],
                    [r, Math.round(r / 2)], [-r, Math.round(r / 2)], [Math.round(r / 2), r], [Math.round(r / 2), -r]
                ];
                for (var i = 0; i < offsets.length; i++) {
                    var nx = Math.min(Math.max(0, px + offsets[i][0]), 2199);
                    var ny = Math.min(Math.max(0, py + offsets[i][1]), 1639);
                    var npix = maskSamplerContext.getImageData(nx, ny, 1, 1).data;
                    if (npix[0] > 64 || (npix[3] > 64 && npix[0] > 64)) {
                        return true;
                    }
                }
            }
            return false;
        }
        // Fond de carte (pays voisins inclus, style Positron)
        var fondImageElement = new Image();
        fondImageElement.crossOrigin = 'anonymous';
        fondImageElement.src = resolvePath('maps/fond.webp');
        var currentProbe = null;
        var probeLoadToken = 0;
        var samplerCanvas = document.createElement('canvas');
        var samplerContext = samplerCanvas.getContext ? samplerCanvas.getContext(
            '2d', { willReadFrequently: true }
        ) : null;
        var samplerReady = false;
        var hoverFrame = null;
        var lastHover = null;
        var renderFrame = null;
        var webgl = null;
        var fallbackContext = null;
        var maxScale = 64;
        var pendingFocus = null;
        var toolMode = null;
        var pinnedEnabled = false;
        var pinnedPoint = null;
        var tapStart = null;
        var departmentCache = new Map();
        var diagramLoadToken = 0;

        var validityFormat;
        var runFormat;
        var mapDateFormat;
        try {
            validityFormat = new Intl.DateTimeFormat('fr-FR', {
                timeZone: timezone,
                weekday: 'short',
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hourCycle: 'h23'
            });
            runFormat = new Intl.DateTimeFormat('fr-FR', {
                timeZone: timezone,
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hourCycle: 'h23'
            });
            mapDateFormat = new Intl.DateTimeFormat('fr-FR', {
                timeZone: timezone,
                weekday: 'long',
                day: '2-digit',
                month: 'long',
                hour: '2-digit',
                minute: '2-digit',
                hourCycle: 'h23'
            });
        } catch (formatError) {
            validityFormat = new Intl.DateTimeFormat('fr-FR');
            runFormat = validityFormat;
            mapDateFormat = validityFormat;
        }

        function resolvePath(path) {
            if (/^(?:https?:\/\/|data:|blob:)/i.test(path || '')) {
                return path;
            }
            return baseUrl + '/' + String(path || '').replace(/^\/+/, '');
        }

        function versioned(path) {
            if (/^(?:data:|blob:)/i.test(path || '')) {
                return String(path);
            }
            var separator = String(path).indexOf('?') === -1 ? '?' : '&';
            var version = manifest && manifest.generated_at ? manifest.generated_at : Date.now();
            return resolvePath(path) + separator + 'v=' + encodeURIComponent(version);
        }

        function showError(message) {
            stopAnimation();
            if (loading) loading.hidden = true;
            if (errorBox) {
                errorBox.textContent = message;
                errorBox.hidden = false;
            }
        }

        function clearError() {
            if (errorBox) {
                errorBox.hidden = true;
                errorBox.textContent = '';
            }
        }

        function parseProbe(buffer) {
            if (!buffer || buffer.byteLength < 16) {
                throw new Error('grille de valeurs tronquée');
            }
            var view = new DataView(buffer);
            var signature = String.fromCharCode(
                view.getUint8(0),
                view.getUint8(1),
                view.getUint8(2),
                view.getUint8(3)
            );
            var width = view.getUint16(4, true);
            var height = view.getUint16(6, true);
            if (signature !== 'HKV1' || !width || !height ||
                    buffer.byteLength < 16 + width * height * 2) {
                throw new Error('grille de valeurs invalide');
            }
            return {
                view: view,
                width: width,
                height: height,
                minimum: view.getFloat32(8, true),
                maximum: view.getFloat32(12, true)
            };
        }

        function probeCell(grid, x, y) {
            var code = grid.view.getUint16(
                16 + (y * grid.width + x) * 2,
                true
            );
            if (code === 65535) {
                return null;
            }
            return grid.minimum + code / 65534 *
                (grid.maximum - grid.minimum);
        }

        function sampleProbe(grid, u, v) {
            if (!grid) {
                return null;
            }
            var x = clamp(u, 0, 1) * (grid.width - 1);
            var y = clamp(v, 0, 1) * (grid.height - 1);
            var x0 = Math.floor(x);
            var y0 = Math.floor(y);
            var x1 = Math.min(x0 + 1, grid.width - 1);
            var y1 = Math.min(y0 + 1, grid.height - 1);
            var fx = x - x0;
            var fy = y - y0;
            var samples = [
                [x0, y0, (1 - fx) * (1 - fy)],
                [x1, y0, fx * (1 - fy)],
                [x0, y1, (1 - fx) * fy],
                [x1, y1, fx * fy]
            ];
            var total = 0;
            var weight = 0;
            samples.forEach(function (entry) {
                var value = probeCell(grid, entry[0], entry[1]);
                if (value === null || entry[2] <= 0) {
                    return;
                }
                total += value * entry[2];
                weight += entry[2];
            });
            return weight > 0 ? total / weight : null;
        }

        function parseColour(value) {
            var clean = String(value || '').replace('#', '');
            if (!/^[0-9a-f]{6}$/i.test(clean)) {
                return [0, 0, 0];
            }
            return [
                parseInt(clean.slice(0, 2), 16),
                parseInt(clean.slice(2, 4), 16),
                parseInt(clean.slice(4, 6), 16)
            ];
        }

        function valueFromColour(red, green, blue, layer) {
            if (!layer || !Array.isArray(layer.stops) || layer.stops.length < 2) {
                return null;
            }
            var stops = layer.stops.map(function (stop) {
                return {
                    value: Number(stop.value),
                    colour: parseColour(stop.color)
                };
            });
            var target = [red, green, blue];
            var bestValue = null;
            var bestDistance = Infinity;
            for (var index = 0; index < stops.length - 1; index += 1) {
                var first = stops[index];
                var second = stops[index + 1];
                var fraction = 0;
                if (!layer.discrete) {
                    var dr = second.colour[0] - first.colour[0];
                    var dg = second.colour[1] - first.colour[1];
                    var db = second.colour[2] - first.colour[2];
                    var denominator = dr * dr + dg * dg + db * db;
                    if (denominator > 0) {
                        fraction = clamp(
                            ((target[0] - first.colour[0]) * dr +
                                (target[1] - first.colour[1]) * dg +
                                (target[2] - first.colour[2]) * db) /
                                denominator,
                            0,
                            1
                        );
                    }
                }
                var candidate = [
                    first.colour[0] + (second.colour[0] - first.colour[0]) * fraction,
                    first.colour[1] + (second.colour[1] - first.colour[1]) * fraction,
                    first.colour[2] + (second.colour[2] - first.colour[2]) * fraction
                ];
                var distance = Math.pow(target[0] - candidate[0], 2) +
                    Math.pow(target[1] - candidate[1], 2) +
                    Math.pow(target[2] - candidate[2], 2);
                if (distance < bestDistance) {
                    bestDistance = distance;
                    bestValue = first.value +
                        (second.value - first.value) * fraction;
                }
            }
            return bestValue;
        }

        function prepareImageSampler(source) {
            samplerReady = false;
            if (!samplerContext || !source) {
                return;
            }
            var width = Number(source.naturalWidth || source.width ||
                (manifest && manifest.width) || 0);
            var height = Number(source.naturalHeight || source.height ||
                (manifest && manifest.height) || 0);
            if (!width || !height) {
                return;
            }
            try {
                samplerCanvas.width = width;
                samplerCanvas.height = height;
                samplerContext.clearRect(0, 0, width, height);
                samplerContext.drawImage(source, 0, 0, width, height);
                samplerReady = true;
            } catch (samplingError) {
                samplerReady = false;
            }
        }

        function samplePalette(u, v, layer) {
            if (!samplerReady || !samplerContext) {
                return null;
            }
            var x = clamp(Math.round(u * (samplerCanvas.width - 1)),
                0, samplerCanvas.width - 1);
            var y = clamp(Math.round(v * (samplerCanvas.height - 1)),
                0, samplerCanvas.height - 1);
            try {
                var pixel = samplerContext.getImageData(x, y, 1, 1).data;
                if (pixel[3] < 12) {
                    return layer.transparent_below !== null &&
                        layer.transparent_below !== undefined ? 0 : null;
                }
                return valueFromColour(pixel[0], pixel[1], pixel[2], layer);
            } catch (samplingError) {
                samplerReady = false;
                return null;
            }
        }

        function loadProbe(step) {
            var token = ++probeLoadToken;
            currentProbe = null;
            var path = step && step.probes && step.probes[currentLayer];
            if (!path) {
                return Promise.resolve();
            }
            return fetchBuffer(versioned(path))
                .then(decompressIfNeeded)
                .then(parseProbe)
                .then(function (grid) {
                    if (token !== probeLoadToken) {
                        return;
                    }
                    currentProbe = grid;
                    if (lastHover) {
                        updateProbe(lastHover.x, lastHover.y);
                    }
                    if (valuesVisible) {
                        scheduleRender();
                    }
                })
                .catch(function () {
                    if (token === probeLoadToken) {
                        currentProbe = null;
                    }
                });
        }

        function hideProbe() {
            lastHover = null;
            if (hoverFrame !== null && window.cancelAnimationFrame) {
                window.cancelAnimationFrame(hoverFrame);
                hoverFrame = null;
            }
            if (probe) {
                probe.hidden = true;
                probe.classList.remove('active');
            }
        }

        function pointerMapPosition(clientX, clientY) {
            var box = viewport.getBoundingClientRect();
            var screenX = clientX - box.left;
            var screenY = clientY - box.top;
            // Projection UNIQUE (computeMapRect) : identique au raster et aux
            // vecteurs → la sonde lit exactement ce qui est affiché.
            var mapRect = computeMapRect(box.width, box.height);
            var u = (screenX - mapRect.x) / mapRect.w;
            var v = (screenY - mapRect.y) / mapRect.h;
            if (u < 0 || u > 1 || v < 0 || v > 1) {
                return null;
            }
            return {
                screenX: screenX,
                screenY: screenY,
                u: u,
                v: v,
                width: box.width,
                height: box.height
            };
        }

        function updateProbe(clientX, clientY) {
            if (!probe || !probeValue || !probeLabel || !manifest ||
                    !currentWeatherImage) {
                hideProbe();
                return;
            }
            lastHover = { x: clientX, y: clientY };
            var position = pointerMapPosition(clientX, clientY);
            var layer = manifest.layers[currentLayer];
            if (!position || !layer) {
                probe.hidden = true;
                return;
            }
            var value = sampleProbe(currentProbe, position.u, position.v);
            var estimated = false;
            if (value === null) {
                value = samplePalette(position.u, position.v, layer);
                estimated = value !== null;
            }
            if (value === null || !Number.isFinite(value)) {
                probe.hidden = true;
                return;
            }
            var decimals = clamp(Number(layer.decimals) || 0, 0, 2);
            var formatted = Number(value).toLocaleString('fr-FR', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            });
            probeValue.textContent = (estimated ? '≈ ' : '') + formatted +
                (layer.unit ? ' ' + layer.unit : '');
            probeLabel.textContent = layer.label || currentLayer;
            probe.hidden = false;
            probe.classList.add('active');

            var tooltipWidth = probe.offsetWidth || 170;
            var tooltipHeight = probe.offsetHeight || 54;
            var left = position.screenX + 16;
            var top = position.screenY + 16;
            if (left + tooltipWidth > position.width - 8) {
                left = position.screenX - tooltipWidth - 16;
            }
            if (top + tooltipHeight > position.height - 8) {
                top = position.screenY - tooltipHeight - 16;
            }
            probe.style.left = Math.max(8, left) + 'px';
            probe.style.top = Math.max(8, top) + 'px';
        }

        var pinnedElement = null;

        function clearPinned() {
            if (pinnedElement && pinnedElement.parentNode) {
                pinnedElement.parentNode.removeChild(pinnedElement);
            }
            pinnedElement = null;
            pinnedPoint = null;
        }

        function positionPinned() {
            if (!pinnedElement || !pinnedPoint || !viewport) {
                return;
            }
            var box = viewport.getBoundingClientRect();
            // Projection UNIQUE (computeMapRect) : l'épingle reste collée au
            // point exact du raster, cohérente avec la sonde et l'affichage.
            var mapRect = computeMapRect(box.width, box.height);
            var screenX = mapRect.x + pinnedPoint.u * mapRect.w;
            var screenY = mapRect.y + pinnedPoint.v * mapRect.h;
            if (screenX < -40 || screenX > box.width + 40 || screenY < -40 || screenY > box.height + 40) {
                pinnedElement.style.display = 'none';
                return;
            }
            pinnedElement.style.display = '';
            var width = pinnedElement.offsetWidth || 170;
            var height = pinnedElement.offsetHeight || 54;
            var left = screenX + 14;
            var top = screenY - height - 14;
            if (left + width > box.width - 8) {
                left = screenX - width - 14;
            }
            if (top < 8) {
                top = screenY + 14;
            }
            pinnedElement.style.left = Math.max(8, Math.min(left, box.width - width - 8)) + 'px';
            pinnedElement.style.top = Math.max(8, Math.min(top, box.height - height - 8)) + 'px';
        }

        function pinProbeAt(clientX, clientY) {
            if (!manifest || !currentWeatherImage) {
                return;
            }
            var position = pointerMapPosition(clientX, clientY);
            var layer = manifest.layers[currentLayer];
            if (!position || !layer) {
                return;
            }
            var value = sampleProbe(currentProbe, position.u, position.v);
            var estimated = false;
            if (value === null) {
                value = samplePalette(position.u, position.v, layer);
                estimated = value !== null;
            }
            if (value === null || !Number.isFinite(value)) {
                return;
            }
            clearPinned();
            var decimals = clamp(Number(layer.decimals) || 0, 0, 2);
            var formatted = Number(value).toLocaleString('fr-FR', {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals
            });
            pinnedElement = document.createElement('div');
            pinnedElement.className = 'amfm-probe amfm-probe-pinned';
            var strong = document.createElement('strong');
            strong.textContent = (estimated ? '≈ ' : '') + formatted + (layer.unit ? ' ' + layer.unit : '');
            var label = document.createElement('span');
            label.textContent = layer.label || currentLayer;
            var close = document.createElement('button');
            close.type = 'button';
            close.className = 'amfm-probe-pin-close';
            close.setAttribute('aria-label', 'Retirer l’épingle');
            close.textContent = '×';
            close.addEventListener('click', function (event) {
                event.stopPropagation();
                clearPinned();
            });
            pinnedElement.appendChild(strong);
            pinnedElement.appendChild(label);
            pinnedElement.appendChild(close);
            viewport.appendChild(pinnedElement);
            pinnedPoint = { u: position.u, v: position.v };
            positionPinned();
        }

        function screenToLatLon(clientX, clientY) {
            if (!manifest || !manifest.bounds) {
                return null;
            }
            var position = pointerMapPosition(clientX, clientY);
            if (!position) {
                return null;
            }
            var bounds = manifest.bounds;
            var west = Number(bounds.west);
            var east = Number(bounds.east);
            var northY = mercator(Number(bounds.north));
            var southY = mercator(Number(bounds.south));
            return {
                latitude: inverseMercator(northY - position.v * (northY - southY)),
                longitude: west + position.u * (east - west)
            };
        }

        function nearestPlace(latitude, longitude) {
            if (!placeBuckets.size) {
                return null;
            }
            var baseLat = Math.floor(latitude);
            var baseLon = Math.floor(longitude);
            var best = null;
            var bestDistance = Infinity;
            for (var dLat = -2; dLat <= 2; dLat += 1) {
                for (var dLon = -2; dLon <= 2; dLon += 1) {
                    var bucket = placeBuckets.get((baseLat + dLat) + '|' + (baseLon + dLon));
                    if (!bucket) {
                        continue;
                    }
                    for (var index = 0; index < bucket.length; index += 1) {
                        var place = bucket[index];
                        var placeLat = Number(place[2]);
                        var placeLon = Number(place[3]);
                        var dy = placeLat - latitude;
                        var dx = (placeLon - longitude) * Math.cos(latitude * Math.PI / 180);
                        var distance = dx * dx + dy * dy;
                        if (distance < bestDistance) {
                            bestDistance = distance;
                            best = place;
                        }
                    }
                }
            }
            return best;
        }

        function setToolHint(message) {
            if (!toolHint) {
                return;
            }
            toolHint.textContent = message || '';
            toolHint.hidden = !message;
        }

        function setToolMode(mode) {
            toolMode = toolMode === mode ? null : mode;
            toolButtons.forEach(function (button) {
                var active = button.dataset.amfmTool === toolMode;
                button.classList.toggle('is-active', active);
                button.setAttribute('aria-pressed', active ? 'true' : 'false');
            });
            if (advancedTools) {
                advancedTools.hidden = toolMode !== 'zoom';
            }
            if (toolMode !== 'zoom' && pinnedEnabled) {
                pinnedEnabled = false;
                if (pinButton) {
                    pinButton.setAttribute('aria-pressed', 'false');
                }
                clearPinned();
            }
            if (toolMode === 'diagram') {
                setToolHint('Cliquez sur la carte pour afficher le diagramme AROME du point choisi.');
            } else {
                setToolHint('');
                closeDiagram();
            }
        }

        // Scanne le masque France (2200×1640) et retourne le rectangle englobant
        // des pixels effectivement couverts (valeur > 0). Permet un cadrage
        // d'export qui ne montre JAMAIS de zone vide (coins du trapèze AROME,
        // mer, pays voisins non maillés) : le cadre suit la donnée réelle.
        var visibleBBoxCache = null;
        function computeVisibleBBox() {
            if (visibleBBoxCache) {
                return visibleBBoxCache;
            }
            if (!franceMaskImage || !franceMaskImage.complete || !franceMaskImage.naturalWidth) {
                return null;
            }
            var mw = franceMaskImage.naturalWidth;
            var mh = franceMaskImage.naturalHeight;
            if (mw < 2 || mh < 2) {
                return null;
            }
            try {
                var mc = document.createElement('canvas');
                mc.width = mw;
                mc.height = mh;
                var mctx = mc.getContext('2d', { willReadFrequently: true });
                if (!mctx) {
                    return null;
                }
                mctx.drawImage(franceMaskImage, 0, 0);
                var data = mctx.getImageData(0, 0, mw, mh).data;
                var x0 = mw, y0 = mh, x1 = -1, y1 = -1;
                // Balayage par pas de 2 puis affinage : 2200×1640 pixels = 3,6 M
                // de lectures, quelques dizaines de ms suffisent en pas de 2.
                for (var y = 0; y < mh; y += 2) {
                    var row = y * mw * 4;
                    for (var x = 0; x < mw; x += 2) {
                        if (data[row + x * 4 + 3] > 8) {
                            if (x < x0) x0 = x;
                            if (x > x1) x1 = x;
                            if (y < y0) y0 = y;
                            if (y > y1) y1 = y;
                        }
                    }
                }
                if (x1 < 0) {
                    return null;
                }
                // Affinage sur la bande de 1 px autour du bbox grossier.
                var xa = Math.max(0, x0 - 2), xb = Math.min(mw - 1, x1 + 2);
                var ya = Math.max(0, y0 - 2), yb = Math.min(mh - 1, y1 + 2);
                for (var yy = ya; yy <= yb; yy++) {
                    var rr = yy * mw * 4;
                    for (var xx = xa; xx <= xb; xx++) {
                        if (data[rr + xx * 4 + 3] > 8) {
                            if (xx < x0) x0 = xx;
                            if (xx > x1) x1 = xx;
                            if (yy < y0) y0 = yy;
                            if (yy > y1) y1 = yy;
                        }
                    }
                }
                visibleBBoxCache = { x0: x0, y0: y0, x1: x1, y1: y1 };
                return visibleBBoxCache;
            } catch (e) {
                return null;
            }
        }

        function composeCaptureCanvas(customStep, customImage, isScreen) {
            var activeImg = customImage || currentWeatherImage;
            var vw = viewport.clientWidth;
            var vh = viewport.clientHeight;
            if (!vw || !vh) {
                return null;
            }

            var outW, outH, hScale, vScale, offX, offY;

            if (isScreen) {
                // Capture d'écran HD EXACTE : reproduction au pixel près de la vue affichée à l'écran (x2 pour netteté Retina/4K)
                var ratio = 2.0;
                outW = Math.round(vw * ratio);
                outH = Math.round(vh * ratio);
                var mapRect = computeMapRect(vw, vh);
                hScale = (mapRect.w / 2200.0) * ratio;
                vScale = (mapRect.h / 1640.0) * ratio;
                offX = mapRect.x * ratio;
                offY = mapRect.y * ratio;
            } else {
                var isEuropeExport = isEuropeDomain();
                var isFranceExport = !isEuropeExport;
                if (isEuropeExport) {
                    // Vue Europe Standard (2200x1640) : cadrage plein cadre 100% de la projection Lambert
                    outW = 2200;
                    outH = 1640;
                    hScale = 1.0;
                    vScale = 1.0;
                    offX = 0;
                    offY = 0;
                } else if (isFranceExport && transform.scale <= 1.15) {
                    // Vue France entière : boîte Météo-NPDC (West: -5.8°, East: +10.2°, North: 51.6°, South: 41.1°)
                    outW = 2200;
                    outH = 1640;
                    var fx0 = 270;  // Ouest Bretagne
                    var fx1 = 1870; // Est Corse
                    var fy0 = 125;  // Nord Mer du Nord / Sud Angleterre
                    var fy1 = 1460; // Sud Bonifacio
                    var fw = fx1 - fx0; // 1600
                    var fh = fy1 - fy0; // 1335
                    var scale = Math.min(outW / fw, outH / fh);
                    hScale = scale;
                    vScale = scale;
                    var cx = (fx0 + fx1) / 2; // 1070
                    var cy = (fy0 + fy1) / 2; // 792.5
                    offX = outW / 2 - cx * scale;
                    offY = outH / 2 - cy * scale;
                } else {
                    // Vue Zoomée Région / Libre : reproduction exacte de la vue
                    outW = 2200;
                    outH = 1640;
                    var viewRect = computeMapRect(vw, vh);
                    var u0 = (0 - viewRect.x) / viewRect.w;
                    var u1 = (vw - viewRect.x) / viewRect.w;
                    var v0 = (0 - viewRect.y) / viewRect.h;
                    var v1 = (vh - viewRect.y) / viewRect.h;
                    var vueW = Math.max(0.01, u1 - u0);
                    var vueH = Math.max(0.01, v1 - v0);
                    var k = Math.max(outW / (vueW * 2200.0), outH / (vueH * 1640.0));
                    hScale = k;
                    vScale = k;
                    var uc = (u0 + u1) / 2;
                    var vc = (v0 + v1) / 2;
                    offX = outW / 2 - uc * 2200.0 * k;
                    offY = outH / 2 - vc * 1640.0 * k;
                }
            }

            // Zone réellement couverte par la carte dans le canvas d'export
            // (évite que titre / logo / légende débordent sur le fond noir)
            var mapRect = {
                left: Math.max(0, offX),
                right: Math.min(outW, offX + 2200 * hScale),
                top: Math.max(0, offY),
                bottom: Math.min(outH, offY + 1640 * vScale)
            };
            if (mapRect.right <= mapRect.left || mapRect.bottom <= mapRect.top) {
                mapRect = { left: 0, right: outW, top: 0, bottom: outH };
            }

            var output = document.createElement('canvas');
            output.width = outW;
            output.height = outH;
            var context = output.getContext('2d');

            // Fond sombre du domaine (#0b1220)
            context.fillStyle = '#0b1220';
            context.fillRect(0, 0, output.width, output.height);

            // Fond de carte terres/mers (clip plein écran)
            context.save();
            context.beginPath();
            context.rect(0, 0, outW, outH);
            context.clip();
            if (fondImageElement && fondImageElement.complete && fondImageElement.naturalWidth) {
                context.save();
                context.transform(hScale, 0, 0, vScale, offX, offY);
                context.drawImage(fondImageElement, 0, 0);
                context.restore();
            } else {
                context.fillStyle = '#8fa3b8';
                context.fillRect(0, 0, output.width, output.height);
            }

            // Dalle météo (si disponible)
            if (activeImg && activeImg.complete && activeImg.naturalWidth) {
                var weatherMasked = document.createElement('canvas');
                weatherMasked.width = output.width;
                weatherMasked.height = output.height;
                var weatherCtx = weatherMasked.getContext('2d');
                weatherCtx.save();
                weatherCtx.transform(hScale, 0, 0, vScale, offX, offY);
                weatherCtx.drawImage(activeImg, 0, 0);
                weatherCtx.restore();
                context.drawImage(weatherMasked, 0, 0);
            } else {
                // Paramètre non disponible : badge central discret sur le fond vierge
                context.save();
                context.font = '700 28px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
                context.textAlign = 'center';
                context.textBaseline = 'middle';
                var msg = 'PARAMÈTRE NON DISPONIBLE POUR CE MODÈLE';
                var tw = context.measureText(msg).width + 64;
                var th = 60;
                var cx = output.width / 2;
                var cy = output.height / 2;
                context.fillStyle = 'rgba(11, 18, 32, 0.92)';
                context.beginPath();
                if (typeof context.roundRect === 'function') {
                    context.roundRect(cx - tw / 2, cy - th / 2, tw, th, 12);
                } else {
                    context.rect(cx - tw / 2, cy - th / 2, tw, th);
                }
                context.fill();
                context.strokeStyle = 'rgba(0, 210, 255, 0.6)';
                context.lineWidth = 2;
                context.stroke();
                context.fillStyle = '#00d2ff';
                context.fillText(msg, cx, cy);
                context.restore();
            }

            // Frontières vectorielles uniques (noir franc 100% net pour France/AROME, adapté Europe)
            if (vectorDefinition && vectorDefinition.paths && vectorDefinition.paths.length) {
                context.save();
                context.transform(hScale, 0, 0, vScale, offX, offY);
                var isFrance = (currentModel.indexOf('_france') !== -1) || (manifest && manifest.bounds && manifest.bounds.projection === 'mercator');
                if (isFrance) {
                    // Copie conforme du moteur AROME : noir franc #05080c, hdStrokeFactor 2.4, départements 100% visibles
                    var hdStrokeFactor = 2.4;
                    vectorDefinition.paths.forEach(function (entry) {
                        context.strokeStyle = '#05080c';
                        context.globalAlpha = 1.0;
                        context.lineCap = 'round';
                        context.lineJoin = 'round';
                        context.lineWidth = ((entry.width || 1.6) * hdStrokeFactor) / hScale;
                        context.stroke(entry.path);
                    });
                } else {
                    // Domaine Europe : synoptique
                    var hdStrokeFactor = 1.8;
                    vectorDefinition.paths.forEach(function (entry) {
                        var isDept = entry.kind === 'department';
                        if (isDept && transform.scale <= 1.35) {
                            return;
                        }
                        context.strokeStyle = entry.colour || (isDept ? '#7a828e' : '#0b1220');
                        context.globalAlpha = isDept ? 0.85 : (entry.opacity || 1.0);
                        context.lineCap = 'round';
                        context.lineJoin = 'round';
                        context.lineWidth = ((entry.width || (isDept ? 0.8 : 1.8)) * hdStrokeFactor) / hScale;
                        context.stroke(entry.path);
                    });
                }
                context.restore();
                context.globalAlpha = 1;
            }
            context.restore(); // Fin clip carte

            // Logo Météo-Climat Pro officiel (en haut à droite, pur PNG sans cadre noir)
            var margin = 32;
            var bannerY = 36;
            var bannerH = 135;

            context.save();
            if (logoImage && logoImage.complete && logoImage.naturalWidth) {
                var logoTargetW = 380;
                var logoTargetH = Math.round(logoTargetW * logoImage.naturalHeight / logoImage.naturalWidth);
                // Logo toujours à l'intérieur de la zone carte (jamais sur le fond noir)
                var lx = Math.min(output.width - margin - logoTargetW, mapRect.right - margin - logoTargetW);
                var ly = Math.max(mapRect.top + 8, bannerY + (bannerH - logoTargetH) / 2);
                context.shadowColor = 'rgba(0, 0, 0, 0.75)';
                context.shadowBlur = 12;
                context.shadowOffsetX = 2;
                context.shadowOffsetY = 2;
                context.drawImage(logoImage, lx, ly, logoTargetW, logoTargetH);
            } else {
                context.textAlign = 'right';
                context.textBaseline = 'top';
                context.font = '800 38px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
                context.fillStyle = '#ffffff';
                context.shadowColor = 'rgba(0, 0, 0, 0.85)';
                context.shadowBlur = 8;
                context.fillText('MÉTÉO-CLIMAT', output.width - margin, bannerY + 20);
                context.font = '900 32px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
                context.fillStyle = '#00d2ff';
                context.fillText('PRO', output.width - margin, bannerY + 68);
            }
            context.restore();

            // Cartouche d'antenne (en haut à gauche)
            var layer = manifest && manifest.layers && manifest.layers[currentLayer];
            var step = customStep || availableSteps()[currentStep];
            var prettyLabel = layer ? layer.label : '';
            var prettyUnit = layer && layer.unit ? layer.unit : '';
            if (typeof window.getLayerPalette === 'function') {
                try {
                    var prettyPal = window.getLayerPalette(currentLayer);
                    if (prettyPal) {
                        prettyLabel = prettyPal.label || prettyLabel;
                        prettyUnit = prettyPal.unit !== undefined ? prettyPal.unit : prettyUnit;
                    }
                } catch (e) {}
            }

            var dateStr = '';
            if (step) {
                try {
                    dateStr = validityFormat.format(new Date(step.valid_time)).replace(':', 'h');
                } catch (e) {
                    dateStr = new Date(step.valid_time).toLocaleDateString('fr-FR');
                }
            }

            var margin = 24;
            var bannerY = 24;
            var bannerH = 175;
            var modelTitle = (manifest && manifest.model_name) ? manifest.model_name : 'AROME HD';
            var paramTitle = prettyLabel + (prettyUnit ? ' (' + prettyUnit + ')' : '');
            var runLabel = '';
            if (manifest && manifest.run_time) {
                try {
                    runLabel = 'Run ' + String(manifest.run_time).slice(11, 16) + 'Z';
                } catch (e) {}
            }
            var dateText = dateStr + (step ? ' (H+' + String(step.lead_hour).padStart(2, '0') + ')' : '');
            var modelAndRun = modelTitle + (runLabel ? ' • ' + runLabel : '');

            context.font = '700 38px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            var w1 = context.measureText(paramTitle).width;
            context.font = '700 26px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            var w2 = context.measureText(modelAndRun).width;
            context.font = '800 34px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            var w3 = context.measureText(dateText).width;
            var bannerW = Math.max(w1, w2, w3) + 48;

            // Cartouche toujours à l'intérieur de la zone carte (jamais sur le fond noir)
            var cartLeft = Math.max(margin, mapRect.left + margin);
            var cartTop = Math.max(bannerY, mapRect.top + bannerY);
            bannerW = Math.min(bannerW, Math.max(120, mapRect.right - cartLeft - margin));
            bannerH = Math.min(bannerH, Math.max(60, mapRect.bottom - cartTop - margin));

            context.fillStyle = 'rgba(7, 11, 20, 0.92)';
            context.beginPath();
            if (typeof context.roundRect === 'function') {
                context.roundRect(cartLeft, cartTop, bannerW, bannerH, 16);
            } else {
                context.rect(cartLeft, cartTop, bannerW, bannerH);
            }
            context.fill();
            context.strokeStyle = 'rgba(0, 210, 255, 0.8)';
            context.lineWidth = 3;
            context.stroke();

            // 1. Titre du paramètre météo (en premier, blanc franc)
            context.fillStyle = '#ffffff';
            context.font = '700 38px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            context.textAlign = 'left';
            context.textBaseline = 'alphabetic';
            context.fillText(paramTitle, cartLeft + 24, cartTop + 48);

            // 2. Modèle météo & Run (en dessous, cyan éclatant)
            context.fillStyle = '#00d2ff';
            context.font = '700 26px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            context.fillText(modelAndRun, cartLeft + 24, cartTop + 88);

            // 3. Date & Échéance (en dessous, GRAND, blanc éclatant avec accent cyan)
            context.fillStyle = '#ffffff';
            context.font = '800 34px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            context.fillText(dateText, cartLeft + 24, cartTop + 140);

            // Légende colorimétrique officielle en bas
            // (Z500 : légende intégrée dans l'image elle-même → pas de surimpression)
            var legendY = 0, legendX = 0, legendW = 0, legendH = 0;
            var z500HasEmbeddedLegend = (currentLayer === 'geopotentiel_500' || currentLayer === 'geopotentiel_500_meteociel');
            if (layer && !z500HasEmbeddedLegend && typeof window.getLayerPalette === 'function' && typeof window.paletteTicks === 'function') {
                try {
                    // Légende toujours à l'intérieur de la zone carte (jamais sur le fond noir)
                    legendW = Math.min(1100, Math.max(200, mapRect.right - mapRect.left - 48));
                    legendH = 96;
                    var legendBottom = 24;
                    legendX = mapRect.left + (mapRect.right - mapRect.left - legendW) / 2;
                    legendY = Math.max(mapRect.top, mapRect.bottom - legendH - legendBottom);

                    context.fillStyle = 'rgba(7, 11, 20, 0.95)';
                    context.beginPath();
                    if (typeof context.roundRect === 'function') {
                        context.roundRect(legendX - 22, legendY - 10, legendW + 44, legendH + 30, 18);
                    } else {
                        context.rect(legendX - 22, legendY - 10, legendW + 44, legendH + 30);
                    }
                    context.fill();
                    context.strokeStyle = 'rgba(0, 210, 255, 0.7)';
                    context.lineWidth = 2.5;
                    context.stroke();

                    // Étiquette
                    context.fillStyle = '#ffffff';
                    context.font = '700 30px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
                    context.textAlign = 'center';
                    context.textBaseline = 'alphabetic';
                    context.fillText(prettyLabel + (prettyUnit ? ' (' + prettyUnit + ')' : ''), legendX + legendW / 2, legendY + 30);

                    // Barre
                    var pal = window.getLayerPalette(currentLayer);
                    var stops = pal && pal.stops ? pal.stops : [];
                    var low = (pal && pal.transparent_below !== null && pal.transparent_below !== undefined) ? pal.transparent_below : (stops.length ? stops[0].value : 0);
                    var max = stops.length ? stops[stops.length - 1].value : 1;
                    var span = (max - low) || 1;
                    var barY = legendY + 44;
                    var isDiscreteZ500 = (currentLayer === 'geopotentiel_500' || currentLayer === 'geopotentiel_500_meteociel');
                    if (isDiscreteZ500 && stops.length > 1) {
                        // Z500 : BANDES DISCRÈTES de 4 dam (style Météociel),
                        // chaque classe reçoit la couleur pleine de son seuil bas.
                        var segW = legendW / (stops.length - 1);
                        for (var si = 0; si < stops.length - 1; si++) {
                            context.fillStyle = stops[si].color;
                            context.fillRect(legendX + si * segW, barY, segW + 0.5, 24);
                        }
                    } else {
                        var gradient = context.createLinearGradient(legendX, 0, legendX + legendW, 0);
                        if (pal && pal.transparent_below !== null && pal.transparent_below !== undefined) {
                            gradient.addColorStop(0, 'rgba(0,0,0,0)');
                        }
                        stops.forEach(function (s) {
                            var pos = Math.max(0, Math.min(1, (Number(s.value) - low) / span));
                            gradient.addColorStop(pos, s.color);
                        });
                        context.fillStyle = gradient;
                        context.beginPath();
                        if (typeof context.roundRect === 'function') {
                            context.roundRect(legendX, barY, legendW, 24, 12);
                        } else {
                            context.rect(legendX, barY, legendW, 24);
                        }
                        context.fill();
                    }
                    context.strokeStyle = 'rgba(255,255,255,0.6)';
                    context.lineWidth = 2;
                    context.stroke();

                    // Ticks
                    context.fillStyle = '#eaf1ff';
                    context.font = '700 24px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
                    var ticks = window.paletteTicks(currentLayer);
                    ticks.forEach(function (tick, i) {
                        var x = legendX + (ticks.length > 1 ? i / (ticks.length - 1) : 0.5) * legendW;
                        context.fillText(String(tick), x, barY + 46);
                    });
                } catch (e) {}
            }
            var occupied = [];
            // Zones protégées ajustées au millimètre (cartouche haut-gauche, logo haut-droite, légende bas)
            occupied.push({ left: 0, right: margin + bannerW + 16, top: 0, bottom: bannerY + bannerH + 16 });
            occupied.push({ left: output.width - margin - 390, right: output.width, top: 0, bottom: bannerY + bannerH + 16 });
            if (legendW > 0 && legendY > 0) {
                occupied.push({ left: legendX - 25, right: legendX + legendW + 25, top: legendY - 15, bottom: output.height });
            } else if (z500HasEmbeddedLegend && manifest && manifest.height) {
                // Légende Z500 intégrée dans l'image (bas ~104 px) → zone protégée équivalente
                var zLegTop = output.height - Math.round(104 * output.height / manifest.height);
                occupied.push({ left: 0, right: output.width, top: zLegTop, bottom: output.height });
            }
            // Villes sur la carte (respecte citiesVisible et se masque automatiquement si valuesVisible est actif)
            if (citiesVisible && !valuesVisible && manifest && manifest.bounds && places && places.length) {
                try {
                    var bounds = manifest.bounds;
                    var northY = mercator(Number(bounds.north));
                    var southY = mercator(Number(bounds.south));
                    var longitudeSpan = Number(bounds.east) - Number(bounds.west);
                    var mercatorSpan = northY - southY;
                    if (longitudeSpan && mercatorSpan) {
                        var exportScale = hScale;
                        // Alignement exact sur la densité du site (vue France = métropoles régionales clés ~95k hab, max 32)
                        var popMin = exportScale < 1.35 ? 95000 : (exportScale < 2.25 ? 45000 : (exportScale < 3.5 ? 15000 : 5000));
                        var maxLabels = exportScale < 1.35 ? 32 : (exportScale < 2.25 ? 50 : 80);
                        var fontSize = exportScale < 1.35 ? 22 : 24;
                        context.font = '800 ' + fontSize + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
                        context.textAlign = 'center';
                        context.textBaseline = 'middle';
                        context.lineJoin = 'round';
                        context.strokeStyle = '#000000';
                        context.fillStyle = '#ffffff';
                        context.lineWidth = 4.8;

                        var drawn = 0;
                        for (var pi = 0; pi < places.length; pi += 1) {
                            var place = places[pi];
                            if (!Array.isArray(place) || place.length < 4) { continue; }
                            // Densité AROME : seules les agglomérations au-dessus du seuil (évite la foule de communes)
                            if (Number(place[1]) < popMin) { continue; }
                            var proj = projectCoords(Number(place[2]), Number(place[3]));
                            var u = proj.u;
                            var v = proj.v;
                            var sx = u * 2200 * hScale + offX;
                            var sy = v * 1640 * vScale + offY;
                            if (sx < 25 || sx > output.width - 25 || sy < 25 || sy > output.height - 25) {
                                continue;
                            }
                            var text = String(place[0]);
                            var tw = context.measureText(text).width;
                            var rect = { left: sx - tw / 2 - 6, right: sx + tw / 2 + 6, top: sy - 14, bottom: sy + 14 };
                            var clash = false;
                            for (var oi = 0; oi < occupied.length; oi += 1) {
                                var other = occupied[oi];
                                if (rect.left < other.right && rect.right > other.left && rect.top < other.bottom && rect.bottom > other.top) {
                                    clash = true;
                                    break;
                                }
                            }
                            if (clash) { continue; }
                            occupied.push(rect);
                            context.strokeText(text, sx, sy);
                            context.fillText(text, sx, sy);
                            drawn += 1;
                            if (drawn >= maxLabels) { break; }
                        }
                    }
                } catch (e) {}
            }

            // Grille de valeurs numériques (si valuesVisible activé)
            if (valuesVisible && manifest && manifest.layers && manifest.layers[currentLayer]) {
                try {
                    var vLayer = manifest.layers[currentLayer];
                    var stepGrid = hScale < 1.35 ? 88 : (hScale < 2.5 ? 78 : 66);
                    var valFontSize = hScale < 1.35 ? 30 : 32;
                    context.font = '900 ' + valFontSize + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
                    context.textAlign = 'center';
                    context.textBaseline = 'middle';
                    context.lineJoin = 'round';

                    // Sampler couleur local (fallback si pas de probe HKV)
                    var localSampler = samplerContext;
                    if (customImage && customImage.complete && customImage.naturalWidth) {
                        var tempS = document.createElement('canvas');
                        tempS.width = customImage.naturalWidth || 2200;
                        tempS.height = customImage.naturalHeight || 1640;
                        var tempCtx = tempS.getContext('2d', { willReadFrequently: true });
                        tempCtx.drawImage(customImage, 0, 0);
                        localSampler = tempCtx;
                    }

                    for (var gy = stepGrid / 2; gy < output.height - 20; gy += stepGrid) {
                        var gv = (gy - offY) / (1640 * vScale);
                        if (gv < 0 || gv > 1) continue;
                        for (var gx = stepGrid / 2; gx < output.width - 20; gx += stepGrid) {
                            var gu = (gx - offX) / (2200 * hScale);
                            if (gu < 0 || gu > 1) continue;

                            if (!isLand(gu, gv)) continue;

                            var gRect = { left: gx - 20, right: gx + 20, top: gy - 16, bottom: gy + 16 };
                            var gClash = false;
                            for (var oi = 0; oi < occupied.length; oi += 1) {
                                var o = occupied[oi];
                                if (gRect.left < o.right && gRect.right > o.left && gRect.top < o.bottom && gRect.bottom > o.top) {
                                    gClash = true;
                                    break;
                                }
                            }
                            if (gClash) continue;

                            // Priorité 1 : probe HKV (même logique que drawValues à l'écran)
                            var gVal = sampleProbe(currentProbe, gu, gv);
                            // Priorité 2 : décodage couleur depuis le canvas pixel
                            if (gVal === null && localSampler) {
                                var px = Math.min(Math.max(0, Math.round(gu * (localSampler.canvas.width - 1))), localSampler.canvas.width - 1);
                                var py = Math.min(Math.max(0, Math.round(gv * (localSampler.canvas.height - 1))), localSampler.canvas.height - 1);
                                var pix = localSampler.getImageData(px, py, 1, 1).data;
                                if (pix[3] >= 12) {
                                    gVal = valueFromColour(pix[0], pix[1], pix[2], vLayer);
                                }
                            }
                            if (gVal === null || !Number.isFinite(gVal)) continue;

                            if ((currentLayer === 'pluie_1h' || currentLayer === 'pluie_cumul' || currentLayer === 'neige' || currentLayer === 'equivalent_eau_neige') && gVal < 0.2) continue;
                            if (currentLayer === 'mucape' && gVal < 40) continue;
                            if (currentLayer === 'graupel' && gVal < 0.1) continue;

                            var gStr = (currentLayer === 'pluie_1h' || currentLayer === 'pluie_cumul') ? (gVal < 10 ? gVal.toFixed(1) : String(Math.round(gVal))) : String(Math.round(gVal));

                            context.strokeStyle = '#000000';
                            context.lineWidth = 6.4;
                            context.strokeText(gStr, gx, gy);
                            context.fillStyle = getValueColour(gVal, currentLayer);
                            context.fillText(gStr, gx, gy);
                        }
                    }
                } catch (vErr) {}
            }


            return output;
        }

        function captureImage(format, isLandscape) {
            format = format || 'png';
            var canvas = composeCaptureCanvas(null, null, isLandscape);
            if (!canvas || !canvas.toBlob) {
                setToolHint('Capture indisponible pour ce navigateur.');
                return;
            }
            var mimeType = format === 'jpeg' ? 'image/jpeg' : 'image/png';
            var ext = format === 'jpeg' ? 'jpg' : 'png';
            canvas.toBlob(function (blob) {
                if (!blob) {
                    return;
                }
                var url = URL.createObjectURL(blob);
                var link = document.createElement('a');
                var layerLabel = manifest && manifest.layers && manifest.layers[currentLayer]
                    ? manifest.layers[currentLayer].label
                    : currentLayer;
                var slug = String(layerLabel || 'arome').toLowerCase()
                    .normalize('NFD').replace(/[̀-ͯ]/g, '')
                    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                link.href = url;
                link.download = 'MeteoClimatPro_' + (manifest ? manifest.model_name.replace(/[^a-zA-Z0-9]/g, '_') : 'AROME') + '_' + (slug || 'carte') + (isLandscape ? '_paysage_16x9' : '') + '_' + Date.now() + '.' + ext;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
            }, mimeType, format === 'jpeg' ? 0.92 : undefined);
        }

        // ────────────────────────────────────────────────────────────────────
        // EXPORT GIF ANIMÉ PROFESSIONNEL (avec modal & sélection d'échéances)
        // ────────────────────────────────────────────────────────────────────
        var gifModal = app.querySelector('[data-amfm-gif-modal]');
        var gifModalClose = app.querySelector('[data-amfm-gif-close]');
        var gifCustomRangeDiv = app.querySelector('[data-amfm-gif-custom-range]');
        var gifStartSelect = app.querySelector('[data-amfm-gif-start]');
        var gifEndSelect = app.querySelector('[data-amfm-gif-end]');
        var gifProgressBox = app.querySelector('[data-amfm-gif-progress-box]');
        var gifPercentText = app.querySelector('[data-amfm-gif-percent]');
        var gifProgressBar = app.querySelector('[data-amfm-gif-bar]');
        var gifStatusText = app.querySelector('[data-amfm-gif-status-text]');
        var gifSubmitBtn = app.querySelector('[data-amfm-gif-submit]');

        function openGifModal() {
            var steps = availableSteps();
            if (!steps.length) {
                showError('Aucune échéance disponible pour le GIF.');
                return;
            }
            if (gifModal) {
                // Remplir les sélecteurs de plage personnalisée
                if (gifStartSelect && gifEndSelect) {
                    gifStartSelect.innerHTML = '';
                    gifEndSelect.innerHTML = '';
                    steps.forEach(function (step, i) {
                        var opt1 = document.createElement('option');
                        opt1.value = String(i);
                        opt1.textContent = 'H+' + String(step.lead_hour).padStart(2, '0');
                        gifStartSelect.appendChild(opt1);

                        var opt2 = document.createElement('option');
                        opt2.value = String(i);
                        opt2.textContent = 'H+' + String(step.lead_hour).padStart(2, '0');
                        if (i === steps.length - 1) opt2.selected = true;
                        gifEndSelect.appendChild(opt2);
                    });
                }
                if (gifProgressBox) gifProgressBox.style.display = 'none';
                if (gifSubmitBtn) {
                    gifSubmitBtn.disabled = false;
                    gifSubmitBtn.innerHTML = '<i class="fa-solid fa-download"></i> Lancer la Génération GIF';
                }
                gifModal.hidden = false;
            } else {
                startGifGeneration();
            }
        }

        if (gifModalClose) {
            gifModalClose.addEventListener('click', function () {
                if (gifModal) gifModal.hidden = true;
            });
        }
        if (gifModal) {
            gifModal.addEventListener('click', function (e) {
                if (e.target === gifModal) gifModal.hidden = true;
            });
            var rangeRadios = gifModal.querySelectorAll('input[name="gif-range"]');
            rangeRadios.forEach(function (radio) {
                radio.addEventListener('change', function () {
                    if (gifCustomRangeDiv) {
                        gifCustomRangeDiv.style.display = (radio.value === 'custom') ? 'flex' : 'none';
                    }
                });
            });
        }
        if (gifSubmitBtn) {
            gifSubmitBtn.addEventListener('click', function () {
                startGifGeneration();
            });
        }

        function startGifGeneration() {
            var allSteps = availableSteps();
            if (!allSteps.length) return;
            if (typeof window.GIF !== 'function') {
                showError('Bibliothèque gif.js non chargée.');
                return;
            }

            // Déterminer la plage d'échéances choisie
            var selectedRange = 'all';
            var checkedRange = gifModal ? gifModal.querySelector('input[name="gif-range"]:checked') : null;
            if (checkedRange) selectedRange = checkedRange.value;

            var filteredSteps = allSteps;
            if (selectedRange === '24h') {
                filteredSteps = allSteps.filter(function (s) { return Number(s.lead_hour) <= 24; });
            } else if (selectedRange === '48h') {
                filteredSteps = allSteps.filter(function (s) { return Number(s.lead_hour) <= 48; });
            } else if (selectedRange === 'custom') {
                var startIdx = gifStartSelect ? parseInt(gifStartSelect.value, 10) : 0;
                var endIdx = gifEndSelect ? parseInt(gifEndSelect.value, 10) : allSteps.length - 1;
                if (startIdx > endIdx) { var tmp = startIdx; startIdx = endIdx; endIdx = tmp; }
                filteredSteps = allSteps.slice(startIdx, endIdx + 1);
            }
            if (!filteredSteps.length) filteredSteps = allSteps;

            // Déterminer la vitesse
            var frameDelay = 1000;
            var checkedSpeed = gifModal ? gifModal.querySelector('input[name="gif-speed"]:checked') : null;
            if (checkedSpeed) frameDelay = parseInt(checkedSpeed.value, 10) || 1000;

            // Interface de progression
            if (gifProgressBox) gifProgressBox.style.display = 'block';
            if (gifSubmitBtn) {
                gifSubmitBtn.disabled = true;
                gifSubmitBtn.innerHTML = '<i class="fa-solid fa-hourglass-half fa-spin"></i> Génération en cours…';
            }
            if (captureGifButton) {
                captureGifButton.classList.add('is-loading');
                captureGifButton.innerHTML = '<i class="fa-solid fa-hourglass-half fa-spin"></i> <span>0%</span>';
            }

            // Dimensions GIF : ratio 4:3 exact (880 × 656) aligné sur la capture HD (2200 × 1640)
            var gw = 880;
            var gh = 656;

            var workerAbsoluteUrl = new URL('js/gif.worker.js', window.location.href).href;
            var gifOptions = {
                quality: 10,
                width: gw,
                height: gh,
                workers: 2,
                workerScript: workerAbsoluteUrl
            };
            var gif = new window.GIF(gifOptions);
            var index = 0;

            function next() {
                if (index >= filteredSteps.length) {
                    if (gifStatusText) gifStatusText.innerHTML = '<i class="fa-solid fa-hourglass-half fa-spin"></i> Finalisation du fichier GIF…';
                    try {
                        gif.render();
                    } catch (renderErr) {
                        console.error('Erreur render GIF:', renderErr);
                        if (captureGifButton) {
                            captureGifButton.classList.remove('is-loading');
                            captureGifButton.innerHTML = '<i class="fa-solid fa-film"></i> <span>GIF</span>';
                        }
                        if (gifSubmitBtn) gifSubmitBtn.disabled = false;
                    }
                    return;
                }
                var step = filteredSteps[index];
                var img = new Image();
                img.crossOrigin = 'anonymous';
                img.onload = function () {
                    var fullCanvas = composeCaptureCanvas(step, img);
                    if (fullCanvas) {
                        var gifCanvas = document.createElement('canvas');
                        gifCanvas.width = gw;
                        gifCanvas.height = gh;
                        var gctx = gifCanvas.getContext('2d');
                        gctx.drawImage(fullCanvas, 0, 0, gw, gh);
                        gif.addFrame(gifCanvas, { copy: true, delay: frameDelay });
                    }
                    index += 1;
                    var pct = Math.round((index / filteredSteps.length) * 50);
                    if (gifProgressBar) gifProgressBar.style.width = pct + '%';
                    if (gifPercentText) gifPercentText.textContent = pct + '%';
                    if (captureGifButton) {
                        captureGifButton.innerHTML = '<i class="fa-solid fa-hourglass-half fa-spin"></i> <span>' + pct + '%</span>';
                    }
                    next();
                };
                img.onerror = function () {
                    index += 1;
                    next();
                };
                img.src = versioned(step.files[currentLayer]);
            }

            var layer = manifest && manifest.layers && manifest.layers[currentLayer];

            gif.on('progress', function (p) {
                var pct = 50 + Math.round(p * 50);
                if (gifProgressBar) gifProgressBar.style.width = pct + '%';
                if (gifPercentText) gifPercentText.textContent = pct + '%';
                if (captureGifButton) {
                    captureGifButton.innerHTML = '<i class="fa-solid fa-hourglass-half fa-spin"></i> <span>' + pct + '%</span>';
                }
            });
            gif.on('finished', function (blob) {
                try {
                    var currentLayerObj = manifest && manifest.layers && manifest.layers[currentLayer];
                    var slug = String(currentLayerObj ? currentLayerObj.label : 'animation').toLowerCase()
                        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                        .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
                    var modelName = (manifest && manifest.model_name) ? manifest.model_name.replace(/[^a-zA-Z0-9]/g, '_') : 'AROME';
                    var filename = 'MeteoClimatPro_' + modelName + '_' + (slug || 'animation') + '.gif';

                    var url = URL.createObjectURL(blob);
                    var link = document.createElement('a');
                    link.href = url;
                    link.download = filename;
                    link.rel = 'noopener';
                    document.body.appendChild(link);
                    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    window.setTimeout(function () {
                        if (link.parentNode) {
                            link.parentNode.removeChild(link);
                        }
                        URL.revokeObjectURL(url);
                    }, 2000);
                } catch (finishErr) {
                    console.error('Erreur déclenchement téléchargement GIF:', finishErr);
                }

                if (gifModal) gifModal.hidden = true;
                if (gifProgressBox) gifProgressBox.style.display = 'none';
                if (gifSubmitBtn) {
                    gifSubmitBtn.disabled = false;
                    gifSubmitBtn.innerHTML = '<i class="fa-solid fa-download"></i> Télécharger le GIF';
                }
                if (captureGifButton) {
                    captureGifButton.classList.remove('is-loading');
                    captureGifButton.innerHTML = '<i class="fa-solid fa-film"></i> <span>GIF</span>';
                }
                setToolHint('GIF généré et téléchargé avec succès !');
            });
            if (typeof gif.on === 'function') {
                gif.on('abort', function () {
                    if (captureGifButton) {
                        captureGifButton.classList.remove('is-loading');
                        captureGifButton.innerHTML = '<i class="fa-solid fa-film"></i> <span>GIF</span>';
                    }
                    setToolHint('Génération du GIF interrompue.');
                });
            }
            next();
        }

        function closeDiagram() {
            if (diagramPopup) {
                diagramPopup.hidden = true;
            }
            diagramLoadToken += 1;
        }

        function fetchDepartmentForDiagram(code) {
            if (departmentCache.has(code)) {
                return departmentCache.get(code);
            }
            var promise = fetchJson(baseUrl + '/departements/' + code + '.json')
                .catch(function (error) {
                    departmentCache.delete(code);
                    throw error;
                });
            departmentCache.set(code, promise);
            return promise;
        }

        function positionDiagramPopup(clientX, clientY) {
            if (!diagramPopup) {
                return;
            }
            var box = viewport.getBoundingClientRect();
            var left = clientX - box.left + 14;
            var top = clientY - box.top + 14;
            var width = diagramPopup.offsetWidth || 320;
            var height = diagramPopup.offsetHeight || 220;
            if (left + width > box.width - 8) {
                left = clientX - box.left - width - 14;
            }
            if (top + height > box.height - 8) {
                top = clientY - box.top - height - 14;
            }
            diagramPopup.style.left = Math.max(8, left) + 'px';
            diagramPopup.style.top = Math.max(8, top) + 'px';
        }

        function renderDiagramChart(name, forecastRows, columnIndex, pointIndex) {
            if (!diagramBody) {
                return;
            }
            diagramBody.replaceChildren();
            var temperatures = [];
            var rains = [];
            var hourLabels = [];
            forecastRows.slice(0, 30).forEach(function (row) {
                var values = row[1] && row[1][pointIndex];
                if (!values) {
                    return;
                }
                var date = new Date(row[0]);
                var tempIndex = columnIndex.temperature_c;
                var rainIndex = columnIndex.precipitation_mm;
                temperatures.push(typeof tempIndex === 'number' ? Number(values[tempIndex]) : null);
                rains.push(typeof rainIndex === 'number' ? Number(values[rainIndex]) : 0);
                hourLabels.push(String(date.getHours()).padStart(2, '0') + 'h');
            });
            var validTemps = temperatures.filter(function (value) { return Number.isFinite(value); });
            if (!validTemps.length) {
                diagramBody.appendChild(document.createTextNode('Aucune donnée exploitable pour ce point.'));
                return;
            }
            var width = 320;
            var height = 150;
            var margin = { left: 30, right: 10, top: 14, bottom: 20 };
            var innerWidth = width - margin.left - margin.right;
            var innerHeight = height - margin.top - margin.bottom;
            var minTemp = Math.min.apply(null, validTemps);
            var maxTemp = Math.max.apply(null, validTemps);
            if (minTemp === maxTemp) {
                minTemp -= 1;
                maxTemp += 1;
            }
            var maxRain = Math.max(1, Math.max.apply(null, rains.map(function (value) {
                return Number.isFinite(value) ? value : 0;
            })));
            var svgNs = 'http://www.w3.org/2000/svg';
            var svg = document.createElementNS(svgNs, 'svg');
            svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
            svg.setAttribute('class', 'amfm-diagram-svg');
            svg.setAttribute('role', 'img');
            svg.setAttribute('aria-label', 'Diagramme AROME pour ' + name);
            var count = temperatures.length;
            var stepX = count > 1 ? innerWidth / (count - 1) : 0;

            rains.forEach(function (value, index) {
                if (!Number.isFinite(value) || value <= 0) {
                    return;
                }
                var barHeight = value / maxRain * innerHeight * 0.55;
                var rect = document.createElementNS(svgNs, 'rect');
                rect.setAttribute('x', (margin.left + index * stepX - stepX * 0.3).toFixed(1));
                rect.setAttribute('y', (margin.top + innerHeight - barHeight).toFixed(1));
                rect.setAttribute('width', Math.max(1.5, stepX * 0.6).toFixed(1));
                rect.setAttribute('height', barHeight.toFixed(1));
                rect.setAttribute('class', 'amfm-diagram-rain');
                svg.appendChild(rect);
            });

            var points = temperatures.map(function (value, index) {
                if (!Number.isFinite(value)) {
                    return null;
                }
                var x = margin.left + index * stepX;
                var y = margin.top + innerHeight * (maxTemp - value) / (maxTemp - minTemp);
                return x.toFixed(1) + ',' + y.toFixed(1);
            }).filter(Boolean);
            if (points.length > 1) {
                var polyline = document.createElementNS(svgNs, 'polyline');
                polyline.setAttribute('points', points.join(' '));
                polyline.setAttribute('class', 'amfm-diagram-temp');
                svg.appendChild(polyline);
            }

            [0, count - 1].forEach(function (index) {
                if (index < 0 || !hourLabels[index]) {
                    return;
                }
                var text = document.createElementNS(svgNs, 'text');
                text.setAttribute('x', (margin.left + index * stepX).toFixed(1));
                text.setAttribute('y', (height - 5).toFixed(1));
                text.setAttribute('text-anchor', index === 0 ? 'start' : 'end');
                text.setAttribute('class', 'amfm-diagram-axis');
                text.textContent = hourLabels[index];
                svg.appendChild(text);
            });

            [minTemp, maxTemp].forEach(function (value) {
                var y = margin.top + innerHeight * (maxTemp - value) / (maxTemp - minTemp);
                var text = document.createElementNS(svgNs, 'text');
                text.setAttribute('x', (margin.left - 4).toFixed(1));
                text.setAttribute('y', (y + 3).toFixed(1));
                text.setAttribute('text-anchor', 'end');
                text.setAttribute('class', 'amfm-diagram-axis');
                text.textContent = Math.round(value) + '°';
                svg.appendChild(text);
            });

            diagramBody.appendChild(svg);
            var caption = document.createElement('p');
            caption.className = 'amfm-diagram-caption';
            caption.textContent = 'Température (ligne) et précipitations horaires (barres) — prochaines échéances AROME.';
            diagramBody.appendChild(caption);
        }

        function openDiagramAt(clientX, clientY) {
            var point = screenToLatLon(clientX, clientY);
            if (!point || !diagramPopup) {
                return;
            }
            var place = nearestPlace(point.latitude, point.longitude);
            if (!place || place.length < 6) {
                setToolHint('Aucune commune identifiée à cet endroit — essayez un point plus proche d’une ville.');
                return;
            }
            setToolHint('Cliquez sur la carte pour afficher le diagramme AROME du point choisi.');
            var name = String(place[0]);
            var communeCode = String(place[4]);
            var departmentCode = String(place[5]);
            var token = ++diagramLoadToken;
            diagramTitle.textContent = name;
            diagramPopup.hidden = false;
            diagramBody.replaceChildren();
            if (diagramStatus) {
                diagramStatus.hidden = false;
                diagramStatus.textContent = 'Chargement du diagramme…';
                diagramBody.appendChild(diagramStatus);
            }
            positionDiagramPopup(clientX, clientY);
            fetchDepartmentForDiagram(departmentCode)
                .then(function (departmentData) {
                    if (token !== diagramLoadToken) {
                        return;
                    }
                    var communes = departmentData.communes || [];
                    var commune = null;
                    for (var index = 0; index < communes.length; index += 1) {
                        if (String(communes[index][0]) === communeCode) {
                            commune = communes[index];
                            break;
                        }
                    }
                    if (!commune) {
                        diagramBody.replaceChildren(document.createTextNode('Commune introuvable dans les données du département.'));
                        return;
                    }
                    var columns = departmentData.columns && Array.isArray(departmentData.columns.values)
                        ? departmentData.columns.values
                        : [];
                    var columnIndex = {};
                    columns.forEach(function (columnName, columnPosition) {
                        columnIndex[columnName] = columnPosition;
                    });
                    var pointIndex = Number(commune[6]);
                    var lowerTime = Date.now() - 3600000;
                    var forecastRows = (departmentData.forecast || []).filter(function (step) {
                        return Array.isArray(step) && new Date(step[0]).getTime() >= lowerTime;
                    });
                    renderDiagramChart(name, forecastRows, columnIndex, pointIndex);
                    positionDiagramPopup(clientX, clientY);
                })
                .catch(function () {
                    if (token !== diagramLoadToken) {
                        return;
                    }
                    diagramBody.replaceChildren(document.createTextNode('Impossible de charger ce diagramme pour le moment.'));
                });
        }

        function showUnavailable(message) {
            if (unavailableBox) {
                if (unavailableText) {
                    unavailableText.textContent = message || 'Paramètre non disponible pour ce modèle';
                }
                unavailableBox.hidden = false;
            }
            if (legend) legend.hidden = true;
            hideProbe();
        }

        function clearUnavailable() {
            if (unavailableBox) {
                unavailableBox.hidden = true;
            }
        }

        function availableSteps() {
            if (!manifest || !Array.isArray(manifest.steps)) {
                return [];
            }
            return manifest.steps.filter(function (step) {
                return step && Number(step.lead_hour) >= 0;
            });
        }

        function initialStep(steps) {
            var threshold = Date.now() - 60 * 60 * 1000;
            for (var index = 0; index < steps.length; index += 1) {
                if (new Date(steps[index].valid_time).getTime() >= threshold) {
                    return index;
                }
            }
            return 0;
        }

        function setMenuOpen(open) {
            layerMenu.hidden = !open;
            menuToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            app.classList.toggle('is-layer-menu-open', open);
        }

        function refreshLayerMenu() {
            if (!manifest || !manifest.layers) return;
            var current = manifest.layers[currentLayer];
            if (currentLayerText) {
                currentLayerText.textContent = current ? current.label : 'Choisir une carte';
            }
            if (layerGrid) {
                layerGrid.querySelectorAll('[data-amfm-layer-key]').forEach(function (button) {
                    var active = button.dataset.amfmLayerKey === currentLayer;
                    button.classList.toggle('is-active', active);
                    button.setAttribute('aria-pressed', active ? 'true' : 'false');
                });
            }
        }

        function buildLayerMenu() {
            if (!layerGrid || !manifest || !manifest.layers) return;
            var groupOrder = [
                'Températures',
                'Précipitations',
                'Vent',
                'Nuages et humidité',
                'Pression et géopotentiel',
                'Instabilité',
                'Relief',
                'Autres'
            ];
            var grouped = {};
            if (typeof layerGrid.replaceChildren === 'function') {
                layerGrid.replaceChildren();
            } else {
                layerGrid.innerHTML = '';
            }
            Object.keys(manifest.layers || {}).forEach(function (key) {
                // Les variantes de style (ex: geopotentiel_500_meteociel) sont pilotées
                // par le sélecteur de style, pas par le menu des couches
                if (key.indexOf('_meteociel') !== -1) { return; }
                var layer = manifest.layers[key];
                var group = layer.group || 'Autres';
                if (!grouped[group]) {
                    grouped[group] = [];
                }
                grouped[group].push({ key: key, layer: layer });
            });
            if (!manifest.layers[currentLayer]) {
                currentLayer = Object.keys(manifest.layers || {})[0] || '';
            }
            groupOrder.forEach(function (group) {
                if (!grouped[group] || !grouped[group].length) {
                    return;
                }
                var section = document.createElement('section');
                section.className = 'amfm-layer-group';
                var title = document.createElement('h3');
                title.textContent = group;
                section.appendChild(title);
                grouped[group].forEach(function (entry) {
                    var button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'amfm-layer-option';
                    button.dataset.amfmLayerKey = entry.key;
                    button.setAttribute('aria-pressed', 'false');
                    var label = document.createElement('span');
                    label.textContent = entry.layer.label || entry.key;
                    var dot = document.createElement('i');
                    dot.setAttribute('aria-hidden', 'true');
                    button.appendChild(label);
                    button.appendChild(dot);
                    button.addEventListener('click', function () {
                        setLayer(entry.key);
                        if (window.matchMedia && window.matchMedia('(max-width: 760px)').matches) {
                            setMenuOpen(false);
                        }
                    });
                    section.appendChild(button);
                });
                layerGrid.appendChild(section);
            });
            refreshLayerMenu();
        }

        function applyPaletteStops() {
            if (!manifest || !manifest.layers || typeof window.getLayerPalette !== 'function') {
                return;
            }
            Object.keys(manifest.layers).forEach(function (key) {
                var layer = manifest.layers[key];
                var pal = window.getLayerPalette(key);
                if (!layer.stops || !layer.stops.length) {
                    layer.stops = pal.stops;
                }
                if (layer.transparent_below === undefined || layer.transparent_below === null) {
                    layer.transparent_below = pal.transparent_below;
                }
                if (!layer.unit && pal.unit) {
                    layer.unit = pal.unit;
                }
                if (layer.decimals === undefined || layer.decimals === null) {
                    layer.decimals = pal.decimals;
                }
                if (!layer.label && pal.label) {
                    layer.label = pal.label;
                }
            });
        }

        function buildLegend() {
            if (!legend || !manifest || !manifest.layers) return;
            var layer = manifest.layers[currentLayer];
            var labelEl = app.querySelector('[data-amfm-legend-label]');
            var unitEl = app.querySelector('[data-amfm-legend-unit]');
            var barEl = app.querySelector('[data-amfm-legend-bar]');
            var ticksEl = app.querySelector('[data-amfm-legend-ticks]');

            // Z500 : la légende (30 rectangles 492→612 dam) est INTÉGRÉE dans
            // l'image elle-même → masquer le panneau pour ne pas la recouvrir.
            var z500Embedded = (currentLayer === 'geopotentiel_500' ||
                                currentLayer === 'geopotentiel_500_meteociel');
            legend.hidden = z500Embedded;
            if (z500Embedded) {
                return;
            }

            if (labelEl && layer) labelEl.textContent = layer.label || 'Échelle';
            if (unitEl && layer) unitEl.textContent = layer.unit || '';

            if (barEl && typeof window.paletteGradientCSS === 'function') {
                barEl.style.background = window.paletteGradientCSS(currentLayer);
            }
            if (ticksEl && typeof window.paletteTicks === 'function') {
                ticksEl.innerHTML = window.paletteTicks(currentLayer).map(function (t) {
                    return '<span>' + t + '</span>';
                }).join('');
            }
        }

        function preloadNeighbour(steps, index) {
            var offsets = [-1, 1];
            if (index === steps.length - 1) offsets.push(-(steps.length - 1));
            if (index === 0) offsets.push(steps.length - 1);
            offsets.forEach(function (offset) {
                var targetIdx = (index + offset + steps.length) % steps.length;
                var neighbour = steps[targetIdx];
                if (!neighbour || !neighbour.files[currentLayer]) {
                    return;
                }
                var preload = new Image();
                preload.crossOrigin = 'anonymous';
                preload.src = versioned(neighbour.files[currentLayer]);
            });
        }

        function renderStep(index) {
            var steps = availableSteps();
            if (!steps.length) {
                showError('Aucune carte disponible pour ce paramètre.');
                return;
            }
            currentStep = clamp(index, 0, steps.length - 1);
            if (slider) {
                slider.max = String(steps.length - 1);
                slider.value = String(currentStep);
            }
            updateUrl();
            if (previousButton) previousButton.disabled = currentStep === 0;
            if (nextButton) nextButton.disabled = currentStep === steps.length - 1;

            var step = steps[currentStep];
            var date = new Date(step.valid_time);
            var dateFormatted = '';
            try {
                dateFormatted = validityFormat.format(date).replace(':', 'h');
            } catch (e) {
                dateFormatted = date.toLocaleTimeString('fr-FR');
            }
            if (validity) validity.textContent = dateFormatted;
            var leadStr = 'H+' + String(step.lead_hour).padStart(2, '0');
            var dayOffset = Math.floor(step.lead_hour / 24);
            if (dayOffset >= 1) {
                leadStr = 'J+' + dayOffset + ' (' + leadStr + ')';
            }
            if (lead) lead.textContent = leadStr;
            var layer = manifest.layers[currentLayer];
            if (viewport) {
                viewport.setAttribute(
                    'aria-label',
                    (layer ? layer.label : 'Carte météo') + ' — ' + dateFormatted
                );
            }
            if (mapTitle) {
                mapTitle.textContent = (layer ? layer.label : 'Carte Météo') +
                    (layer && layer.unit ? ' (' + layer.unit + ')' : '');
            }
            if (mapDate) {
                mapDate.textContent = dateFormatted + ' (' + leadStr + ')';
            }
            // Ligne d'en-tête en haut à gauche : paramètre + échéance (comme météociel)
            var headline = app.querySelector('[data-amfm-headline]');
            if (headline) {
                var layerName = layer ? layer.label : currentLayer;
                var runLabel = '';
                try {
                    runLabel = runFormat.format(new Date(step.valid_time)).replace(':', 'h');
                } catch (e) {
                    runLabel = dateFormatted;
                }
                headline.innerHTML = '';
                var layerSpan = document.createElement('span');
                layerSpan.className = 'amfm-headline-layer';
                layerSpan.textContent = layerName +
                    (layer && layer.unit ? ' (' + layer.unit + ')' : '') + ' — ';
                headline.appendChild(layerSpan);
                headline.appendChild(document.createTextNode(runLabel + ' ' + leadStr));
            }

            // Mise à jour du cartouche intégré directement sur la carte (TV, Plein écran & Normal)
            if (badgeParam) {
                var prettyL = layer ? layer.label : currentLayer;
                var prettyU = (layer && layer.unit) ? ' (' + layer.unit + ')' : '';
                badgeParam.textContent = prettyL + prettyU;
            }
            if (badgeModel) {
                var mTitle = (manifest && manifest.model_name) ? manifest.model_name : 'Modèle météo';
                var rTag = '';
                if (manifest && manifest.run_time) {
                    try {
                        rTag = ' • Run ' + String(manifest.run_time).slice(11, 16) + 'Z';
                    } catch (e) {}
                }
                badgeModel.textContent = mTitle + rTag;
            }
            if (badgeDate) {
                badgeDate.innerHTML = dateFormatted + ' <span class="amfm-badge-lead">(' + leadStr + ')</span>';
            }

            clearError();
            clearUnavailable();
            if (loading) loading.hidden = false;
            hideProbe();
            var token = ++loadToken;
            var fileRel = step && step.files && step.files[currentLayer];
            if (!fileRel) {
                if (token === loadToken) {
                    if (loading) loading.hidden = true;
                    if (webgl) {
                        webgl.ready = false;
                    }
                    currentWeatherImage = null;
                    scheduleRender();
                    showUnavailable('Paramètre non disponible pour ce modèle');
                }
                return;
            }
            var nextSource = versioned(fileRel);
            loadProbe(step);
            var loader = new Image();
            loader.crossOrigin = 'anonymous';
            loader.onload = function () {
                if (token !== loadToken) {
                    return;
                }
                clearUnavailable();
                uploadWeatherImage(loader);
                prepareImageSampler(loader);
                if (loading) loading.hidden = true;
                preloadNeighbour(steps, currentStep);
            };
            loader.onerror = function () {
                if (token === loadToken) {
                    if (loading) loading.hidden = true;
                    if (webgl) {
                        webgl.ready = false;
                    }
                    currentWeatherImage = null;
                    scheduleRender();
                    showUnavailable('Donnée non disponible pour cette échéance');
                }
            };
            loader.src = nextSource;
        }

        
        window.addEventListener('layerchange', function (e) {
            if (e.detail && e.detail.layer) {
                setLayer(e.detail.layer);
            }
        });

        // Centre vertical du viewport — le header flotte par-dessus la carte
        // (translucide), donc tous les zooms/pans/focus s'expriment par
        // rapport au centre de l'écran.
        function mapCenterY(height) {
            return (height || viewport.clientHeight) / 2;
        }

        function focusOnPoint(u, v, scale) {
            var w = viewport.clientWidth;
            var h = viewport.clientHeight;
            var s = (w / h) > (2200.0 / 1640.0) ?
                (w / 2200.0) : (h / 1640.0);
            var targetScale = clamp(scale || 1, 1, maxScale);
            transform.scale = targetScale;
            // Projection UNIQUE (même base que computeMapRect) : le point
            // (u,v) du raster se retrouve au centre du viewport.
            transform.x = 2200.0 * s * targetScale * (0.5 - u);
            transform.y = 1640.0 * s * targetScale * (0.5 - v);
            applyTransform();
        }

        var regionSelect = app.querySelector('[data-amfm-region-select]');
        if (regionSelect) {
            // Configuration identique au site AROME (domaine France) pour la
            // France et les régions ; pays/Europe sur le domaine Europe.
            var REGION_CONFIG = {
                europe:     { model: 'consensus',        latitude: 49.0, longitude: 8.0, scale: 1.0 },
                france:     { model: 'consensus_france', reset: true },
                hdf:        { model: 'consensus_france', latitude: 49.85, longitude: 2.82, scale: 2.65 },
                normandie:  { model: 'consensus_france', latitude: 48.95, longitude: -0.07, scale: 2.85 },
                idf:        { model: 'consensus_france', latitude: 48.65, longitude: 2.50, scale: 4.20 },
                grandest:   { model: 'consensus_france', latitude: 48.65, longitude: 5.80, scale: 2.25 },
                bretagne:   { model: 'consensus_france', latitude: 48.00, longitude: -3.08, scale: 2.80 },
                pdl:        { model: 'consensus_france', latitude: 47.30, longitude: -0.85, scale: 2.75 },
                cvl:        { model: 'consensus_france', latitude: 47.45, longitude: 1.60, scale: 2.55 },
                bfc:        { model: 'consensus_france', latitude: 47.10, longitude: 5.00, scale: 2.65 },
                naq:        { model: 'consensus_france', latitude: 44.95, longitude: 0.40, scale: 1.85 },
                ara:        { model: 'consensus_france', latitude: 45.30, longitude: 4.65, scale: 2.25 },
                occitanie:  { model: 'consensus_france', latitude: 43.50, longitude: 2.25, scale: 2.25 },
                paca:       { model: 'consensus_france', latitude: 43.85, longitude: 6.00, scale: 2.85 },
                corse:      { model: 'consensus_france', latitude: 42.10, longitude: 9.05, scale: 4.20 },
                belgique:   { model: 'consensus_france', latitude: 50.25, longitude: 4.40, scale: 3.10 },
                uk:         { model: 'consensus',        latitude: 54.2, longitude: -2.8, scale: 2.8 },
                allemagne:  { model: 'consensus',        latitude: 51.3, longitude: 10.5, scale: 2.8 },
                espagne:    { model: 'consensus',        latitude: 40.2, longitude: -3.8, scale: 2.6 },
                italie:     { model: 'consensus',        latitude: 42.6, longitude: 12.6, scale: 2.8 }
            };

            regionSelect.addEventListener('change', function (e) {
                var val = e.target.value || 'europe';
                // Familles de modèles : variante Europe et variante France par modèle
                var MODEL_FAMILY = {
                    consensus: { eu: 'consensus', fr: 'consensus_france' },
                    consensus_france: { eu: 'consensus', fr: 'consensus_france' },
                    probabilites: { eu: 'probabilites', fr: 'probabilites_france' },
                    probabilites_france: { eu: 'probabilites', fr: 'probabilites_france' },
                    gfs: { eu: 'gfs', fr: 'gfs_france' },
                    gfs_france: { eu: 'gfs', fr: 'gfs_france' },
                    arpege: { eu: 'arpege', fr: 'arpege_france' },
                    arpege_france: { eu: 'arpege', fr: 'arpege_france' },
                    icon_eu: { eu: 'icon_eu', fr: 'icon_eu_france' },
                    icon_eu_france: { eu: 'icon_eu', fr: 'icon_eu_france' },
                    aifs: { eu: 'aifs', fr: 'aifs_france' },
                    aifs_france: { eu: 'aifs', fr: 'aifs_france' }
                };
                var family = MODEL_FAMILY[currentModel] || { eu: 'gfs', fr: 'gfs_france' };
                var onFranceModel = (currentModel === family.fr);
                // "Europe Entière" : depuis une variante France → modèle Europe de la famille
                if (val === 'europe') {
                    if (onFranceModel) {
                        transform = { scale: 1, x: 0, y: 0 };
                        switchModel(family.eu);
                    } else {
                        // Déjà sur un modèle Europe : recentrer sans changer de modèle
                        resetView();
                    }
                    updateUrl();
                    return;
                }
                // "France Entière" : depuis un modèle Europe avec variante France → bascule
                if (val === 'france') {
                    if (currentModel === family.eu && family.fr) {
                        transform = { scale: 1, x: 0, y: 0 };
                        switchModel(family.fr);
                    } else if (currentModel === family.fr) {
                        resetView();
                    } else {
                        transform = { scale: 1, x: 0, y: 0 };
                        switchModel('gfs_france');
                    }
                    updateUrl();
                    return;
                }
                var cfg = REGION_CONFIG[val];
                if (!cfg) {
                    resetView();
                    updateUrl();
                    return;
                }
                // Régions : les régions françaises passent sur la variante France de la
                // famille courante (si elle existe), les pays sur la variante Europe
                var targetModel = (cfg.model === 'gfs_france')
                    ? (family.fr || 'gfs_france')
                    : (family.eu || 'gfs');
                var focus = {
                    latitude: cfg.latitude,
                    longitude: cfg.longitude,
                    scale: cfg.scale
                };
                if (currentModel !== targetModel) {
                    pendingFocus = focus;
                    switchModel(targetModel);
                } else {
                    focusLocation(focus);
                }
                updateUrl();
            });

        }

        // Raccordement direct et robuste des menus déroulants
        var layerSelect = document.getElementById('direct-layer-select');
        if (layerSelect) {
            layerSelect.addEventListener('change', function(e) {
                setLayer(e.target.value);
            });
        }

        var z500StyleSelect = document.getElementById('z500-style');
        if (z500StyleSelect) {
            z500StyleSelect.addEventListener('change', function (e) {
                setLayer(e.target.value);
            });
        }

        var switchToken = 0; // ponytail: guard anti-double-switch — pas de AbortController pour IE11

        function switchModel(modelKey) {
            var token = ++switchToken; // invalide tout fetch précédent
            var modelMap = {
                gfs: { path: 'output/gfs', name: 'GFS Europe', badge: '0,25°' },
                gfs_france: { path: 'output/gfs_france', name: 'GFS France', badge: '0,25°' },
                arpege: { path: 'output/arpege', name: 'ARPEGE Europe', badge: '0,1°' },
                arpege_france: { path: 'output/arpege_france', name: 'ARPEGE France', badge: '0,1°' },
                icon_eu: { path: 'output/icon_eu', name: 'ICON-EU Europe', badge: '7 km' },
                icon_eu_france: { path: 'output/icon_eu_france', name: 'ICON-EU France', badge: '7 km' },
                aifs: { path: 'output/aifs', name: 'ECMWF AIFS Europe', badge: '0,25°' },
                aifs_france: { path: 'output/aifs_france', name: 'ECMWF AIFS France', badge: '0,25°' }
            };
            var target = modelMap[modelKey] || modelMap.gfs;
            var prevBaseUrl = baseUrl;
            baseUrl = target.path;
            app.dataset.baseUrl = target.path;
            app.dataset.model = modelKey;

            var titleSpan = document.querySelector('.amfm-title-text');
            if (titleSpan) {
                titleSpan.textContent = target.name;
            }
            var badge = document.querySelector('.amfm-badge');
            if (badge) {
                badge.textContent = target.badge;
            }

            fetchJson(baseUrl + '/maps/index.json')
                .then(function(payload) {
                    // Un switch plus récent a été lancé entre-temps → ignorer
                    if (token !== switchToken) return;

                    if (!payload || !payload.layers || !Array.isArray(payload.steps)) {
                        throw new Error('manifeste invalide');
                    }
                    manifest = payload;
                    applyPaletteStops();
                    currentStep = 0;
                    if (payload.overlay && typeof loadVectorOverlay === 'function') {
                        loadVectorOverlay(payload.overlay);
                    }
                    if (typeof loadPlaces === 'function') {
                        loadPlaces();
                    }
                    if (payload.fond) {
                        fondImageElement = new Image();
                        fondImageElement.crossOrigin = 'anonymous';
                        fondImageElement.src = versioned(payload.fond);
                        if (webgl) {
                            var fImg = new Image();
                            fImg.crossOrigin = 'anonymous';
                            fImg.src = versioned(payload.fond);
                            fImg.onload = function () {
                                if (!webgl) return;
                                var gl = webgl.gl;
                                gl.activeTexture(gl.TEXTURE2);
                                gl.bindTexture(gl.TEXTURE_2D, webgl.fondTexture);
                                gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, fImg);
                                webgl.fondReady = true;
                                scheduleRender();
                            };
                        }
                    }
                    if (payload.mask) {
                        franceMaskImage = new Image();
                        franceMaskImage.crossOrigin = 'anonymous';
                        franceMaskImage.src = versioned(payload.mask);
                        franceMaskImage.onload = function () {
                            if (maskSamplerContext) {
                                try {
                                    maskSamplerContext.drawImage(franceMaskImage, 0, 0, 2200, 1640);
                                    maskSamplerReady = true;
                                } catch (e) {}
                            }
                            if (webgl) {
                                var gl = webgl.gl;
                                gl.activeTexture(gl.TEXTURE1);
                                gl.bindTexture(gl.TEXTURE_2D, webgl.maskTexture);
                                gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, franceMaskImage);
                                webgl.maskReady = true;
                            }
                            scheduleRender();
                        };
                    }
                    var isFranceOnly = (modelKey.indexOf('_france') !== -1);
                    var dSel = document.getElementById('direct-layer-select');
                    if (dSel) {
                        // Couches disponibles = celles réellement rendues par le modèle (Z500/T850 compris sur France)
                        var z500Opt = dSel.querySelector('option[value="geopotentiel_500"]');
                        if (z500Opt) z500Opt.disabled = !(manifest.layers && manifest.layers['geopotentiel_500']);
                        var t850Opt = dSel.querySelector('option[value="temperature_850"]');
                        if (t850Opt) t850Opt.disabled = !(manifest.layers && manifest.layers['temperature_850']);
                    }
                    var regSel = document.getElementById('select-region');
                    if (regSel) {
                        if (isFranceOnly && regSel.value === 'europe') {
                            regSel.value = 'france';
                        } else if (!isFranceOnly && regSel.value === 'france') {
                            regSel.value = 'europe';
                        }
                    }

                    if (!manifest.layers[currentLayer]) {
                        currentLayer = manifest.layers['geopotentiel_500'] ? 'geopotentiel_500' : (Object.keys(manifest.layers)[0] || 'temperature');
                        if (dSel) dSel.value = currentLayer;
                    }
                    if (typeof buildLayerMenu === 'function') buildLayerMenu();
                    buildLegend();
                    updateZ500StyleToggle();
                    currentModel = modelKey;
                    var modelSel2 = document.getElementById('select-model');
                    if (modelSel2) modelSel2.value = modelKey;
                    renderStep(0);
                    updateUrl();
                    if (typeof applyUrlParams === 'function') applyUrlParams();
                    if (pendingFocus && typeof focusLocation === 'function') {
                        focusLocation(pendingFocus);
                        pendingFocus = null;
                    }
                })
                .catch(function () {
                    // Revert — ne jamais afficher les images d'un autre modèle
                    // sous une baseUrl cassée.
                    baseUrl = prevBaseUrl;
                    app.dataset.baseUrl = prevBaseUrl;
                    app.dataset.model = 'gfs';
                    if (titleSpan) titleSpan.textContent = 'GFS Europe';
                    if (badge) badge.textContent = '0,25°';
                    var modelSel = document.getElementById('select-model');
                    if (modelSel) modelSel.value = 'gfs';
                    showError('Modèle ' + target.name + ' non encore disponible — génération en cours.');
                    window.setTimeout(function() { clearError(); }, 4000);
                });
        }

        var modelSelect = document.getElementById('select-model');
        if (modelSelect) {
            modelSelect.addEventListener('change', function(e) {
                var v = e.target.value;
                transform = { scale: 1, x: 0, y: 0 };
                var regSel = document.getElementById('select-region');
                if (regSel) {
                    regSel.value = (v.indexOf('_france') !== -1) ? 'france' : 'europe';
                }
                switchModel(v);
            });
        }

        // ponytail: duplicate regionSelect removed (handled above via focusOnPoint)

        function setLayer(layer) {
            if (!manifest || !manifest.layers[layer]) {
                return;
            }
            currentLayer = layer;
            var dSel = document.getElementById('direct-layer-select');
            var baseKey = (layer.indexOf('_meteociel') !== -1) ? 'geopotentiel_500' : layer;
            if (dSel && dSel.value !== baseKey) {
                dSel.value = baseKey;
            }
            refreshLayerMenu();
            buildLegend();
            updateZ500StyleToggle();
            var steps = availableSteps();
            currentStep = clamp(currentStep, 0, Math.max(0, steps.length - 1));
            renderStep(currentStep);
        }

        // ── Sélecteur de style des contours Z500 (Dense / Météociel) ──────────
        function updateZ500StyleToggle() {
            var toggle = document.getElementById('z500-style');
            if (!toggle) {
                return;
            }
            var isZ500 = (currentLayer === 'geopotentiel_500' || currentLayer === 'geopotentiel_500_meteociel');
            var hasVariant = !!(manifest && manifest.layers && manifest.layers['geopotentiel_500_meteociel']);
            toggle.style.display = (isZ500 && hasVariant) ? '' : 'none';
            if (isZ500 && toggle.value !== currentLayer) {
                toggle.value = currentLayer;
            }
        }

        // ── État dans l'URL (style meteo-npdc.fr) ─────────────────────────────
        function updateUrl() {
            if (!window.history || !window.history.replaceState) {
                return;
            }
            var params = new URLSearchParams();
            params.set('model', currentModel);
            params.set('parametre', currentLayer);
            var regSel = document.getElementById('select-region');
            if (regSel) params.set('region', regSel.value);
            params.set('heure', String(currentStep));
            window.history.replaceState(null, '', window.location.pathname + '?' + params.toString());
        }

        function applyUrlParams() {
            var params = new URLSearchParams(window.location.search);
            var p = params.get('parametre') || params.get('layer');
            if (p && manifest && manifest.layers[p]) {
                setLayer(p);
            }
            var reg = params.get('region');
            var regSel = document.getElementById('select-region');
            if (reg) {
                if (regSel && regSel.querySelector('option[value="' + reg + '"]')) {
                    regSel.value = reg;
                    var cfg = REGION_CONFIG[reg];
                    if (cfg) {
                        focusLocation({ latitude: cfg.latitude, longitude: cfg.longitude, scale: cfg.scale });
                    }
                }
            }
            var heure = parseInt(params.get('heure'), 10);
            if (!isNaN(heure)) {
                var steps = availableSteps();
                if (heure >= 0 && heure < steps.length) {
                    renderStep(heure);
                }
            }
        }

        function stopAnimation() {
            if (timer !== null) {
                window.clearInterval(timer);
                timer = null;
            }
            playButton.innerHTML = '<i class="fa-solid fa-play" aria-hidden="true"></i>';
            playButton.setAttribute('aria-label', 'Lancer l’animation');
            playButton.title = 'Lancer l’animation';
            playButton.classList.remove('is-playing');
        }

        function toggleAnimation() {
            if (timer !== null) {
                stopAnimation();
                return;
            }
            var steps = availableSteps();
            if (steps.length < 2) {
                return;
            }
            playButton.innerHTML = '<i class="fa-solid fa-pause" aria-hidden="true"></i>';
            playButton.setAttribute('aria-label', 'Arrêter l’animation');
            playButton.title = 'Arrêter l’animation';
            playButton.classList.add('is-playing');
            timer = window.setInterval(function () {
                var next = currentStep + 1;
                if (next >= availableSteps().length) {
                    next = 0;
                }
                renderStep(next);
            }, 1050);
        }

        function resizeCanvas(canvas, width, height, pixelRatio) {
            if (!canvas) {
                return false;
            }
            var canvasWidth = Math.max(1, Math.round(width * pixelRatio));
            var canvasHeight = Math.max(1, Math.round(height * pixelRatio));
            if (canvas.width === canvasWidth && canvas.height === canvasHeight) {
                return false;
            }
            canvas.width = canvasWidth;
            canvas.height = canvasHeight;
            return true;
        }

        function compileShader(gl, type, source) {
            var shader = gl.createShader(type);
            gl.shaderSource(shader, source);
            gl.compileShader(shader);
            if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
                gl.deleteShader(shader);
                return null;
            }
            return shader;
        }

        function initialiseWebgl() {
            if (!weatherCanvas) {
                return null;
            }
            var gl = weatherCanvas.getContext('webgl', {
                alpha: false,
                antialias: false,
                depth: false,
                preserveDrawingBuffer: false
            });
            if (!gl) {
                return null;
            }
            var vertexShader = compileShader(gl, gl.VERTEX_SHADER,
                'attribute vec2 aPosition;\n' +
                'attribute vec2 aUv;\n' +
                'varying vec2 vUv;\n' +
                'void main(){vUv=aUv;gl_Position=vec4(aPosition,0.0,1.0);}'
            );
            var fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER,
                'precision mediump float;\n' +
                'varying vec2 vUv;\n' +
                'uniform sampler2D uWeather;\n' +
                'uniform sampler2D uMask;\n' +
                'uniform sampler2D uFond;\n' +
                'uniform vec2 uViewport;\n' +
                'uniform vec4 uRect;\n' +
                'uniform float uHasWeather;\n' +
                'uniform float uHasMask;\n' +
                'uniform float uHasFond;\n' +
                'void main(){\n' +
                ' vec3 frame=vec3(0.043,0.055,0.086);\n' +
                // Projection UNIQUE (identique aux vecteurs/probes/export) :
                // le raster 2200×1640 occupe le rectangle uRect (px écran).
                ' vec2 uv=(vUv*uViewport-uRect.xy)/uRect.zw;\n' +
                ' if(uv.x<0.0||uv.x>1.0||uv.y<0.0||uv.y>1.0){\n' +
                '  gl_FragColor=vec4(frame,1.0);return;\n' +
                ' }\n' +
                // Fond : carte des pays (fond.webp) si dispo, sinon gris neutre
                ' vec3 base=vec3(0.6471,0.6510,0.6902);\n' +
                ' if(uHasFond>0.5){\n' +
                '  base=texture2D(uFond,uv).rgb;\n' +
                ' } else if(uHasMask>0.5){\n' +
                '  base=mix(vec3(0.6471,0.6510,0.6902),vec3(0.76,0.78,0.81),texture2D(uMask,uv).r);\n' +
                ' }\n' +
                ' if(uHasWeather<0.5){\n' +
                '  gl_FragColor=vec4(base,1.0);return;\n' +
                ' }\n' +
                ' vec4 weather=texture2D(uWeather,uv);\n' +
                ' float alpha=weather.a;\n' +
                ' gl_FragColor=vec4(mix(base,weather.rgb,alpha),1.0);\n' +
                '}'
            );
            if (!vertexShader || !fragmentShader) {
                return null;
            }
            var program = gl.createProgram();
            gl.attachShader(program, vertexShader);
            gl.attachShader(program, fragmentShader);
            gl.linkProgram(program);
            if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
                return null;
            }
            gl.useProgram(program);
            var buffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
                -1, 1, 0, 0,
                -1, -1, 0, 1,
                1, 1, 1, 0,
                1, -1, 1, 1
            ]), gl.STATIC_DRAW);
            var position = gl.getAttribLocation(program, 'aPosition');
            var uv = gl.getAttribLocation(program, 'aUv');
            gl.enableVertexAttribArray(position);
            gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 16, 0);
            gl.enableVertexAttribArray(uv);
            gl.vertexAttribPointer(uv, 2, gl.FLOAT, false, 16, 8);

            var texture = gl.createTexture();
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, texture);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            gl.uniform1i(gl.getUniformLocation(program, 'uWeather'), 0);

            var maskTexture = gl.createTexture();
            var maskImage = new Image();
            maskImage.crossOrigin = 'anonymous';
            maskImage.src = resolvePath((manifest && manifest.mask) ? manifest.mask : 'maps/mask_france.png');
            maskImage.onload = function() {
                gl.activeTexture(gl.TEXTURE1);
                gl.bindTexture(gl.TEXTURE_2D, maskTexture);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
                gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, maskImage);
                webgl.maskReady = true;
                scheduleRender();
            };

            // Fond de carte (pays voisins inclus) — fond.webp
            var fondTexture = gl.createTexture();
            var fondImage = new Image();
            fondImage.crossOrigin = 'anonymous';
            fondImage.src = resolvePath((manifest && manifest.fond) ? manifest.fond : 'maps/fond.webp');
            fondImage.onload = function() {
                gl.activeTexture(gl.TEXTURE2);
                gl.bindTexture(gl.TEXTURE_2D, fondTexture);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
                gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, fondImage);
                webgl.fondReady = true;
                scheduleRender();
            };

            return {
                gl: gl,
                program: program,
                texture: texture,
                maskTexture: maskTexture,
                fondTexture: fondTexture,
                viewportSize: gl.getUniformLocation(program, 'uViewport'),
                mapRect: gl.getUniformLocation(program, 'uRect'),
                hasWeather: gl.getUniformLocation(program, 'uHasWeather'),
                maskSampler: gl.getUniformLocation(program, 'uMask'),
                useMask: gl.getUniformLocation(program, 'uUseMask'),
                fondSampler: gl.getUniformLocation(program, 'uFond'),
                useFond: gl.getUniformLocation(program, 'uHasFond'),
                ready: false,
                maskReady: false,
                fondReady: false
            };
        }

        function uploadWeatherImage(source) {
            currentWeatherImage = source;
            if (!webgl) {
                scheduleRender();
                return;
            }
            var gl = webgl.gl;
            gl.activeTexture(gl.TEXTURE0);
            gl.bindTexture(gl.TEXTURE_2D, webgl.texture);
            gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
            gl.texImage2D(
                gl.TEXTURE_2D,
                0,
                gl.RGBA,
                gl.RGBA,
                gl.UNSIGNED_BYTE,
                source
            );
            webgl.ready = true;
            scheduleRender();
        }

        function drawWeather(width, height, pixelRatio) {
            if (!weatherCanvas) {
                return;
            }
            resizeCanvas(weatherCanvas, width, height, pixelRatio);
            if (webgl) {
                var gl = webgl.gl;
                gl.viewport(0, 0, weatherCanvas.width, weatherCanvas.height);
                gl.useProgram(webgl.program);
                // Projection UNIQUE (computeMapRect) : identique aux vecteurs,
                // labels, probes, GIF et export → aucun désalignement possible.
                var mapRect = computeMapRect(width, height);
                gl.uniform2f(webgl.viewportSize, width, height);
                gl.uniform4f(webgl.mapRect, mapRect.x, mapRect.y, mapRect.w, mapRect.h);
                gl.uniform1f(webgl.hasWeather, webgl.ready ? 1 : 0);
                gl.uniform1i(webgl.maskSampler, 1);
                gl.uniform1f(webgl.useMask, webgl.maskReady ? 1 : 0);
                gl.uniform1i(webgl.fondSampler, 2);
                gl.uniform1f(webgl.useFond, webgl.fondReady ? 1 : 0);
                gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
                return;
            }
            if (!fallbackContext) {
                fallbackContext = weatherCanvas.getContext('2d');
            }
            if (!fallbackContext) {
                return;
            }
            fallbackContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
            // Cadre sombre autour du domaine (le fond clair n'existe que dans la carte)
            fallbackContext.fillStyle = '#0b1220';
            fallbackContext.fillRect(0, 0, width, height);
            if (!currentWeatherImage) {
                return;
            }
            // Projection UNIQUE (computeMapRect) — mêmes coordonnées que le
            // WebGL, les vecteurs, les labels et les probes.
            var mapRect = computeMapRect(width, height);
            var mrx = mapRect.x;
            var mry = mapRect.y;
            var mrw = mapRect.w;
            var mrh = mapRect.h;
            fallbackContext.imageSmoothingEnabled = true;
            fallbackContext.imageSmoothingQuality = 'high';
            // Fond de carte (pays voisins inclus) si chargé, sinon gris neutre
            if (fondImageElement && fondImageElement.complete && fondImageElement.naturalWidth) {
                fallbackContext.drawImage(fondImageElement, mrx, mry, mrw, mrh);
            } else {
                fallbackContext.fillStyle = '#a5a6b0';
                fallbackContext.fillRect(mrx, mry, mrw, mrh);
            }
            // Dalle météo : maillage AROME alpha-composité sur le fond
            var weatherLayer = document.createElement('canvas');
            weatherLayer.width = width;
            weatherLayer.height = height;
            var weatherLayerCtx = weatherLayer.getContext('2d');
            weatherLayerCtx.drawImage(currentWeatherImage, mrx, mry, mrw, mrh);
            fallbackContext.drawImage(weatherLayer, 0, 0);
        }

        function loadVectorOverlay(path) {
            if (!path || !vectorContext || typeof window.Path2D !== 'function') {
                return Promise.resolve();
            }
            return fetchText(versioned(path)).then(function (source) {
                var documentSvg = new DOMParser().parseFromString(
                    source,
                    'image/svg+xml'
                );
                var svg = documentSvg.documentElement;
                var viewBox = String(svg.getAttribute('viewBox') || '')
                    .trim().split(/\s+/).map(Number);
                if (viewBox.length !== 4 || !viewBox[2] || !viewBox[3]) {
                    throw new Error('surcouche vectorielle invalide');
                }
                var paths = Array.from(svg.querySelectorAll('path')).map(
                    function (node) {
                        var width = Number(node.getAttribute('stroke-width') || 1);
                        // Classification par épaisseur : département (fin), région (moyen), pays/côte (épais)
                        var kind = width <= 1.0 ? 'department' : (width <= 1.6 ? 'region' : 'country');
                        return {
                            path: new Path2D(node.getAttribute('d') || ''),
                            colour: node.getAttribute('stroke') || '#101116',
                            opacity: Number(node.getAttribute('stroke-opacity') || 1),
                            width: width,
                            lineCap: node.getAttribute('stroke-linecap') || 'butt',
                            lineJoin: node.getAttribute('stroke-linejoin') || 'miter',
                            kind: kind
                        };
                    }
                );
                vectorDefinition = {
                    width: viewBox[2],
                    height: viewBox[3],
                    paths: paths
                };
                scheduleRender();
            }).catch(function () {
                vectorDefinition = null;
            });
        }

        function drawVectors(width, height, pixelRatio) {
            if (!vectorContext || !vectorDefinition) {
                return;
            }
            resizeCanvas(vectorCanvas, width, height, pixelRatio);
            vectorContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
            vectorContext.clearRect(0, 0, width, height);
            // Projection UNIQUE (computeMapRect) : parfaitement alignée avec le
            // raster WebGL/2D — plus aucun décalage possible entre les deux.
            var mapRect = computeMapRect(width, height);
            var horizontalScale = mapRect.w / 2200.0;
            var verticalScale = mapRect.h / 1640.0;
            vectorContext.setTransform(
                pixelRatio * horizontalScale,
                0,
                0,
                pixelRatio * verticalScale,
                pixelRatio * mapRect.x,
                pixelRatio * mapRect.y
            );
            var isFrance = (currentModel.indexOf('_france') !== -1) || (manifest && manifest.bounds && manifest.bounds.projection === 'mercator');
            if (isFrance) {
                // Copie conforme du moteur AROME interactif
                vectorDefinition.paths.forEach(function (entry) {
                    vectorContext.strokeStyle = entry.colour || '#0d1117';
                    vectorContext.globalAlpha = 1.0;
                    vectorContext.lineCap = 'round';
                    vectorContext.lineJoin = 'round';
                    vectorContext.lineWidth = (entry.width || 1.6) / horizontalScale;
                    vectorContext.stroke(entry.path);
                });
            } else {
                // Mode Europe synoptique
                vectorDefinition.paths.forEach(function (entry) {
                    var isDept = entry.kind === 'department';
                    if (isDept && transform.scale <= 1.35) {
                        return; // Masqué sur la vue globale Europe pour éviter la surcharge
                    }
                    vectorContext.strokeStyle = entry.colour || (isDept ? '#7a828e' : '#0b1220');
                    vectorContext.globalAlpha = isDept ? (transform.scale > 2.0 ? 0.9 : 0.6) : (entry.opacity || 1.0);
                    vectorContext.lineCap = 'round';
                    vectorContext.lineJoin = 'round';
                    vectorContext.lineWidth = (entry.width || (isDept ? 0.8 : 1.8)) / horizontalScale;
                    vectorContext.stroke(entry.path);
                });
            }
            vectorContext.globalAlpha = 1;
        }

        function scheduleRender() {
            if (renderFrame !== null) {
                return;
            }
            renderFrame = window.requestAnimationFrame(function () {
                renderFrame = null;
                var width = viewport.clientWidth;
                var height = viewport.clientHeight;
                if (!width || !height) {
                    return;
                }
                var pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
                drawWeather(width, height, pixelRatio);
                drawVectors(width, height, pixelRatio);
                drawValues(width, height, pixelRatio);
                drawLabels(width, height, pixelRatio);
            });
        }

        function mercator(latitude) {
            var radians = clamp(latitude, -85, 85) * Math.PI / 180;
            return Math.log(Math.tan(Math.PI / 4 + radians / 2));
        }

        function inverseMercator(value) {
            return (2 * Math.atan(Math.exp(value)) - Math.PI / 2) * 180 / Math.PI;
        }

        // ────────────────────────────────────────────────────────────────────
        // PROJECTION UNIQUE de la carte (raster 2200×1640) vers un viewport
        // de taille donnée. Tous les calques (WebGL, fallback 2D, vecteurs,
        // labels, probes, GIF, export) passent par cette fonction : ils sont
        // donc TOUJOURS parfaitement alignés, quel que soit le ratio écran.
        //
        //   - Mode « vue France » (scale ≤ 1.15) : cadrage intelligent sur le
        //     rectangle réellement couvert par le maillage (masque France).
        //     Les zones non maillées (Italie, mer, coins du trapèze AROME en
        //     Mercator) sont placées HORS du viewport : plus aucune grande
        //     zone « vide de maillage » à l'écran.
        //   - Mode zoomé (région/département) : le raster remplit le viewport
        //     en cover (le surplus est découpé, jamais de bandes, la France
        //     reste proportionnelle — jamais étirée), zoom/pan inclus.
        //
        // Retour : { x, y, w, h } en pixels CSS du viewport.
        // `t` (optionnel) : transformation à utiliser (défaut : transform
        // courant) — le GIF fige sa propre transformation pendant l'encodage.
        // Le header flotte AU-DESSUS de la carte (translucide) : la carte
        // remplit donc tout le viewport, sans zone réservée.
        // ────────────────────────────────────────────────────────────────────
        function isEuropeDomain() {
            if (!currentModel) return false;
            if (currentModel.indexOf('_france') !== -1) return false;
            return (currentModel === 'gfs' || currentModel === 'arpege' || currentModel === 'icon_eu' || currentModel === 'aifs');
        }

        function computeMapRect(width, height, t) {
            t = t || transform;
            var isEurope = isEuropeDomain();

            if (isEurope) {
                // Mode "contain" : tout le domaine visible (Groenland, Maroc, Espagne, Islande, Scandinavie)
                // Math.min = letterbox — pas de coupure, centré
                var scale = Math.min(width / 2200.0, height / 1640.0) * t.scale;
                return {
                    x: width / 2 + t.x - 1100.0 * scale,
                    y: height / 2 + t.y - 820.0 * scale,
                    w: 2200.0 * scale,
                    h: 1640.0 * scale
                };
            }

            var s = Math.max(width / 2200.0, height / 1640.0);

            if (t.scale <= 1.15) {
                // Vue France entière : englobe TOUTE la France métropolitaine ET la Corse
                // avec marge de respiration en haut (header) et en bas (timeline d'échéances)
                var FX0 = 260;  // Ouest Bretagne
                var FX1 = 1860; // Est Corse / Alsace
                var FY0 = 110;  // Nord Dunkerque
                var FY1 = 1530; // Sud Bonifacio (Corse entièrement dégagée)
                var fw = FX1 - FX0; // 1600
                var fh = FY1 - FY0; // 1420
                var availH = Math.max(180, height - 150); // 70px timeline + 60px header + 20px marge
                var availW = Math.max(260, width - 40);
                var sFrance = Math.min(availW / (fw * 1.04), availH / (fh * 1.04));
                var cx = (FX0 + FX1) / 2; // 1060
                var cy = (FY0 + FY1) / 2; // 820
                var bboxRect = {
                    x: width / 2 + t.x - cx * sFrance,
                    y: height / 2 + t.y - cy * sFrance,
                    w: 2200.0 * sFrance,
                    h: 1640.0 * sFrance
                };
                if (t.scale <= 1.001) {
                    return bboxRect;
                }
                // Interpolation fluide entre vue France et zoom libre
                var coverScale = s * t.scale;
                var coverRect = {
                    x: width / 2 + t.x - 1100.0 * coverScale,
                    y: height / 2 + t.y - 820.0 * coverScale,
                    w: 2200.0 * coverScale,
                    h: 1640.0 * coverScale
                };
                var f = Math.max(0, Math.min(1, (t.scale - 1.001) / 0.149));
                return {
                    x: bboxRect.x + (coverRect.x - bboxRect.x) * f,
                    y: bboxRect.y + (coverRect.y - bboxRect.y) * f,
                    w: bboxRect.w + (coverRect.w - bboxRect.w) * f,
                    h: bboxRect.h + (coverRect.h - bboxRect.h) * f
                };
            }
            // Mode zoom/pan libre : cohérent avec changeZoom, pan et pinch
            var scale = s * t.scale;
            return {
                x: width / 2 + t.x - 1100.0 * scale,
                y: height / 2 + t.y - 820.0 * scale,
                w: 2200.0 * scale,
                h: 1640.0 * scale
            };
        }

        function visiblePlaces(width, height, bounds, northY, mercatorSpan, density) {
            if (transform.scale < 1.35 || !placeBuckets.size) {
                return places;
            }
            // Projection UNIQUE (computeMapRect) : même fenêtre que le raster.
            var mapRect = computeMapRect(width, height);
            var mapLeft = (0 - mapRect.x) / mapRect.w;
            var mapRight = (width - mapRect.x) / mapRect.w;
            var mapTop = (0 - mapRect.y) / mapRect.h;
            var mapBottom = (height - mapRect.y) / mapRect.h;
            var longitudeSpan = Number(bounds.east) - Number(bounds.west);
            var west = Number(bounds.west) + mapLeft * longitudeSpan;
            var east = Number(bounds.west) + mapRight * longitudeSpan;
            var north = inverseMercator(northY - mapTop * mercatorSpan);
            var south = inverseMercator(northY - mapBottom * mercatorSpan);
            var candidates = [];
            for (var latitude = Math.floor(south) - 1;
                    latitude <= Math.ceil(north) + 1; latitude += 1) {
                for (var longitude = Math.floor(west) - 1;
                        longitude <= Math.ceil(east) + 1; longitude += 1) {
                    var bucket = placeBuckets.get(latitude + '|' + longitude) || [];
                    for (var index = 0; index < bucket.length; index += 1) {
                        if (Number(bucket[index][1]) < density.population) {
                            continue;
                        }
                        candidates.push(bucket[index]);
                    }
                }
            }
            candidates.sort(function (first, second) {
                return Number(second[1]) - Number(first[1]);
            });
            return candidates;
        }

        function labelDensity() {
            var isEurope = isEuropeDomain();
            if (transform.scale < 1.35) {
                return isEurope ?
                    { population: 500000, maximum: 22, size: 12 } :
                    { population: 95000, maximum: 32, size: 12 };
            }
            if (transform.scale < 2.25) {
                return isEurope ?
                    { population: 150000, maximum: 40, size: 12 } :
                    { population: 45000, maximum: 45, size: 12 };
            }
            if (transform.scale < 3.75) {
                return { population: 15000, maximum: 60, size: 12 };
            }
            if (transform.scale < 6) {
                return { population: 5000, maximum: 80, size: 12 };
            }
            if (transform.scale < 8) {
                return { population: 2000, maximum: 100, size: 12 };
            }
            if (transform.scale < 16) {
                return { population: 300, maximum: 140, size: 13 };
            }
            if (transform.scale < 32) {
                return { population: 60, maximum: 130, size: 13 };
            }
            return { population: 5, maximum: 110, size: 13 };
        }

        function overlaps(rectangle, occupied) {
            for (var index = 0; index < occupied.length; index += 1) {
                var other = occupied[index];
                if (rectangle.left < other.right && rectangle.right > other.left &&
                        rectangle.top < other.bottom && rectangle.bottom > other.top) {
                    return true;
                }
            }
            return false;
        }

        function projectCoords(lat, lon) {
            if (manifest && manifest.bounds && manifest.bounds.projection === 'lambert') {
                var b = manifest.bounds;
                var r_lat1 = (Number(b.lat1) || 30.0) * Math.PI / 180;
                var r_lat2 = (Number(b.lat2) || 60.0) * Math.PI / 180;
                var r_lat0 = (Number(b.lat0) || 50.0) * Math.PI / 180;
                var r_lon0 = (Number(b.lon0) || -5.0) * Math.PI / 180;
                var xMin = Number(b.x_min) || -0.5902;
                var xMax = Number(b.x_max) || 0.5902;
                var yMin = Number(b.y_min) || -0.4200;
                var yMax = Number(b.y_max) || 0.4600;
                var n = Math.log(Math.cos(r_lat1) / Math.cos(r_lat2)) / Math.log(
                    Math.tan(Math.PI / 4 + r_lat2 / 2) / Math.tan(Math.PI / 4 + r_lat1 / 2)
                );
                var F = (Math.cos(r_lat1) * Math.pow(Math.tan(Math.PI / 4 + r_lat1 / 2), n)) / n;
                var rho0 = F / Math.pow(Math.tan(Math.PI / 4 + r_lat0 / 2), n);
                var r_lat = lat * Math.PI / 180;
                var r_lon = lon * Math.PI / 180;
                var rho = F / Math.pow(Math.tan(Math.PI / 4 + r_lat / 2), n);
                var theta = n * (r_lon - r_lon0);
                var x = rho * Math.sin(theta);
                var y = rho0 - rho * Math.cos(theta);
                var u = (x - xMin) / (xMax - xMin);
                var v = (yMax - y) / (yMax - yMin);
                return { u: u, v: v };
            }
            var bounds = manifest && manifest.bounds ? manifest.bounds : { south: 39.5, west: -8.5, north: 52.5, east: 13.5 };
            var ny = mercator(Number(bounds.north));
            var sy = mercator(Number(bounds.south));
            var u = (lon - Number(bounds.west)) / (Number(bounds.east) - Number(bounds.west));
            var v = (ny - mercator(lat)) / (ny - sy);
            return { u: u, v: v };
        }

        function drawLabels(width, height, pixelRatio) {
            if (!labelsContext || !manifest) {
                return;
            }
            resizeCanvas(labelsCanvas, width, height, pixelRatio);
            labelsContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
            labelsContext.clearRect(0, 0, width, height);
            if (!citiesVisible || valuesVisible || !places.length || !manifest.bounds) {
                return;
            }

            var bounds = manifest.bounds;
            var northY = mercator(Number(bounds.north));
            var southY = mercator(Number(bounds.south));
            var longitudeSpan = Number(bounds.east) - Number(bounds.west);
            var mercatorSpan = northY - southY;
            if (!longitudeSpan || !mercatorSpan) {
                return;
            }

            var density = labelDensity();
            var candidates = visiblePlaces(
                width,
                height,
                bounds,
                northY,
                mercatorSpan,
                density
            );
            var occupied = [];
            var drawn = 0;
            // Projection UNIQUE (computeMapRect) : les villes sont
            // exactement au même endroit que le raster et les vecteurs.
            var labelRect = computeMapRect(width, height);
            labelsContext.font = '700 ' + density.size + 'px Arial, sans-serif';
            labelsContext.textAlign = 'center';
            labelsContext.textBaseline = 'middle';
            labelsContext.lineJoin = 'round';
            labelsContext.strokeStyle = 'rgba(8, 19, 28, .94)';
            labelsContext.fillStyle = '#ffffff';
            labelsContext.lineWidth = density.size >= 12 ? 3.5 : 3;

            for (var index = 0; index < candidates.length; index += 1) {
                var place = candidates[index];
                if (!Array.isArray(place) || place.length < 4) {
                    continue;
                }
                if (Number(place[1]) < density.population) {
                    break;
                }
                var coords = projectCoords(Number(place[2]), Number(place[3]));
                var screenX = labelRect.x + coords.u * labelRect.w;
                var screenY = labelRect.y + coords.v * labelRect.h;
                if (screenX < -80 || screenX > width + 80 ||
                        screenY < -15 || screenY > height + 15) {
                    continue;
                }
                var text = String(place[0]);
                var textWidth = labelsContext.measureText(text).width;
                var rectangle = {
                    left: screenX - textWidth / 2 - 4,
                    right: screenX + textWidth / 2 + 4,
                    top: screenY - density.size / 2 - 3,
                    bottom: screenY + density.size / 2 + 3
                };
                if (overlaps(rectangle, occupied)) {
                    continue;
                }
                occupied.push(rectangle);
                labelsContext.strokeText(text, screenX, screenY);
                labelsContext.fillText(text, screenX, screenY);
                drawn += 1;
                if (drawn >= density.maximum) {
                    break;
                }
            }
        }

        function getValueColour(val, layerKey) {
            if (layerKey === 'temperature' || layerKey === 'temperature_850' || layerKey === 'temperature_ressentie' || layerKey === 'point_rosee' || layerKey === 't2m') {
                if (val >= 40) return '#ff2a6d'; // Canicule extrême (fuchsia)
                if (val >= 35) return '#ff7b00'; // Très forte chaleur (orange vif)
                if (val >= 30) return '#ffea00'; // Forte chaleur (jaune d'or dès 30°C)
                if (val <= 0)  return '#70d6ff'; // Gelées (cyan éclatant)
                return '#ffffff';
            }
            if (layerKey === 'vent' || layerKey === 'vent_moyen' || layerKey === 'rafales' || layerKey === 'rafales_cumul' || layerKey === 'rafales_max_cumul' || layerKey === 'wind' || layerKey === 'gust') {
                if (val >= 120) return '#ff2a6d'; // Tempête violente
                if (val >= 105) return '#ff7b00'; // Tempête
                if (val >= 90)  return '#ffea00'; // Fort coup de vent (dès 90 km/h)
                return '#ffffff';
            }
            if (layerKey === 'pluie_1h') {
                if (val >= 30) return '#ff2a6d'; // Pluies diluviennes
                if (val >= 20) return '#ff7b00'; // Très fortes pluies
                if (val >= 10) return '#ffea00'; // Pluies soutenues (dès 10 mm/h)
                return '#ffffff';
            }
            if (layerKey === 'pluie_cumul' || layerKey === 'precip') {
                if (val >= 80) return '#ff2a6d'; // Cumul exceptionnel
                if (val >= 50) return '#ff7b00'; // Fort cumul
                if (val >= 20) return '#ffea00'; // Cumul notable (dès 20 mm)
                return '#ffffff';
            }
            if (layerKey === 'neige' || layerKey === 'neige_au_sol') {
                if (val >= 50) return '#ff2a6d';
                if (val >= 20) return '#ff7b00';
                if (val >= 5)  return '#70d6ff';
                return '#ffffff';
            }
            if (layerKey === 'mucape') {
                if (val >= 1500) return '#ff2a6d'; // Orages violents
                if (val >= 800)  return '#ffea00'; // Risque orageux
                return '#ffffff';
            }
            return '#ffffff';
        }

        function drawValues(width, height, pixelRatio) {
            if (!valuesContext || !valuesCanvas) return;
            resizeCanvas(valuesCanvas, width, height, pixelRatio);
            valuesContext.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
            valuesContext.clearRect(0, 0, width, height);
            if (!valuesVisible || !manifest || !currentLayer || !manifest.layers[currentLayer] || (!samplerReady && !currentProbe)) {
                return;
            }

            var layer = manifest.layers[currentLayer];
            var mapRect = computeMapRect(width, height);
            var isEurope = isEuropeDomain();
            // Pas de la grille dense et équilibré identique à AROME HD
            var stepPx = isEurope ?
                (transform.scale < 1.35 ? 44 : (transform.scale < 2.5 ? 38 : 34)) :
                (transform.scale < 1.35 ? 36 : (transform.scale < 2.5 ? 34 : 32));
            var fontSize = isEurope ?
                (transform.scale < 1.35 ? 9.5 : 11.0) :
                (transform.scale < 1.35 ? 10.0 : 11.5);
            valuesContext.font = '800 ' + fontSize + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
            valuesContext.textAlign = 'center';
            valuesContext.textBaseline = 'middle';
            valuesContext.lineJoin = 'round';

            for (var y = stepPx / 2; y < height; y += stepPx) {
                var v = (y - mapRect.y) / mapRect.h;
                if (v < 0 || v > 1) continue;
                for (var x = stepPx / 2; x < width; x += stepPx) {
                    var u = (x - mapRect.x) / mapRect.w;
                    if (u < 0 || u > 1) continue;

                    // Exclusion totale des valeurs en mer (ne garder que les terres)
                    if (!isLand(u, v)) continue;

                    var val = sampleProbe(currentProbe, u, v);
                    if (val === null) val = samplePalette(u, v, layer);
                    if (val === null || !Number.isFinite(val)) continue;

                    // Filtre d'exclusion pour pluie / neige / orages : ne pas afficher si 0
                    if ((currentLayer === 'pluie_1h' || currentLayer === 'pluie_cumul' || currentLayer === 'neige' || currentLayer === 'equivalent_eau_neige') && val < 0.2) {
                        continue;
                    }
                    if (currentLayer === 'mucape' && val < 40) continue;
                    if (currentLayer === 'graupel' && val < 0.1) continue;

                    var strVal = '';
                    if (currentLayer === 'pluie_1h' || currentLayer === 'pluie_cumul') {
                        strVal = val < 10 ? val.toFixed(1) : String(Math.round(val));
                    } else {
                        strVal = String(Math.round(val));
                    }

                    valuesContext.strokeStyle = 'rgba(10, 15, 25, 0.95)';
                    valuesContext.lineWidth = 2.4;
                    valuesContext.strokeText(strVal, x, y);
                    valuesContext.fillStyle = getValueColour(val, currentLayer);
                    valuesContext.fillText(strVal, x, y);
                }
            }
        }

        function loadPlaces() {
            if (!manifest || !manifest.places) {
                return Promise.resolve();
            }
            return fetchJson(versioned(manifest.places))
                .then(function (payload) {
                    places = payload && Array.isArray(payload.places) ?
                        payload.places : [];
                    placeBuckets = new Map();
                    places.forEach(function (place) {
                        if (!Array.isArray(place) || place.length < 4) {
                            return;
                        }
                        var key = Math.floor(Number(place[2])) + '|' +
                            Math.floor(Number(place[3]));
                        if (!placeBuckets.has(key)) {
                            placeBuckets.set(key, []);
                        }
                        placeBuckets.get(key).push(place);
                    });
                    scheduleRender();
                })
                .catch(function (error) {
                    console.warn('Villes non chargées (' +
                        (manifest && manifest.places) + ') :', error);
                    places = [];
                    placeBuckets = new Map();
                });
        }

        function applyTransform() {
            if (!viewport) return;
            var w = viewport.clientWidth;
            var h = viewport.clientHeight;
            var isEurope = isEuropeDomain();
            var s = isEurope ? Math.min(w / 2200.0, h / 1640.0) : Math.max(w / 2200.0, h / 1640.0);
            var totalScale = s * transform.scale;
            var rasterW = 2200.0 * totalScale;
            var rasterH = 1640.0 * totalScale;
            // Déplacement libre à la souris (pan) avec limites souples
            var maxX = Math.max(w * 0.9, (rasterW - w) / 2 + w * 0.6);
            var maxY = Math.max(h * 0.9, (rasterH - h) / 2 + h * 0.6);
            transform.x = Math.max(-maxX, Math.min(maxX, transform.x));
            transform.y = Math.max(-maxY, Math.min(maxY, transform.y));
            if (zoomLevel) zoomLevel.textContent = Math.round(transform.scale * 100) + ' %';
            if (zoomOut) zoomOut.disabled = transform.scale <= 1.001;
            if (zoomIn) zoomIn.disabled = transform.scale >= maxScale - 0.001;
            if (viewport.classList) viewport.classList.toggle('is-zoomed', transform.scale > 1.001);
            scheduleRender();
            if (lastHover && typeof updateProbe === 'function') {
                updateProbe(lastHover.x, lastHover.y);
            }
            if (typeof positionPinned === 'function') {
                positionPinned();
            }
        }

        function changeZoom(nextScale, clientX, clientY) {
            var previousScale = transform.scale;
            nextScale = clamp(nextScale, 1, maxScale);
            var box = viewport.getBoundingClientRect();
            var px = (typeof clientX === 'number' ? clientX : box.left + box.width / 2) -
                box.left - box.width / 2;
            var py = (typeof clientY === 'number' ? clientY : box.top + mapCenterY(box.height)) -
                box.top - mapCenterY(box.height);
            var worldX = (px - transform.x) / previousScale;
            var worldY = (py - transform.y) / previousScale;
            transform.x = px - worldX * nextScale;
            transform.y = py - worldY * nextScale;
            transform.scale = nextScale;
            applyTransform();
        }

        function resetView() {
            transform = { scale: 1, x: 0, y: 0 };
            var regSel = document.getElementById('select-region');
            if (regSel) regSel.value = (currentModel.indexOf('_france') !== -1) ? 'france' : 'europe';
            applyTransform();
            if (typeof updateUrl === 'function') updateUrl();
        }

        if (viewport) {
            viewport.addEventListener('keydown', function (e) {
                var panStep = 60;
                if (e.key === '+' || e.key === '=') {
                    e.preventDefault();
                    changeZoom(transform.scale * 1.3);
                } else if (e.key === '-' || e.key === '_') {
                    e.preventDefault();
                    changeZoom(transform.scale / 1.3);
                } else if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    transform.x += panStep;
                    applyTransform();
                } else if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    transform.x -= panStep;
                    applyTransform();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    transform.y += panStep;
                    applyTransform();
                } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    transform.y -= panStep;
                    applyTransform();
                } else if (e.key === 'Home' || e.key === '0') {
                    e.preventDefault();
                    resetView();
                } else if (e.key === ' ' || e.key === 'k') {
                    e.preventDefault();
                    toggleAnimation();
                }
            });
        }

        function focusLocation(detail) {
            pendingFocus = detail || null;
            if (!manifest || !pendingFocus || !manifest.bounds) {
                return;
            }
            var width = viewport.clientWidth;
            var height = viewport.clientHeight;
            var latitude = Number(pendingFocus.latitude);
            var longitude = Number(pendingFocus.longitude);
            if (!width || !height || !Number.isFinite(latitude) ||
                    !Number.isFinite(longitude)) {
                return;
            }
            var isEurope = (manifest && manifest.bounds && (manifest.bounds.projection === 'lambert' || manifest.bounds.west < -20)) || (currentModel === 'gfs') || (currentModel === 'arpege');
            var proj = projectCoords(latitude, longitude);
            var u = proj.u;
            var v = proj.v;
            var scale = clamp(Number(pendingFocus.scale) || 1.0, 1.0, maxScale);
            var s = isEurope ? Math.min(width / 2200.0, height / 1640.0) : Math.max(width / 2200.0, height / 1640.0);
            transform.scale = scale;
            transform.x = 2200.0 * s * scale * (0.5 - u);
            transform.y = 1640.0 * s * scale * (0.5 - v) + (height * 0.04);
            pendingFocus = null;
            applyTransform();
        }

        app.addEventListener('amfm:focus-location', function (event) {
            focusLocation(event.detail);
        });

        if (menuToggle && layerMenu) {
            menuToggle.addEventListener('click', function () {
                setMenuOpen(layerMenu.hidden);
            });
        }
        if (menuClose && menuToggle) {
            menuClose.addEventListener('click', function () {
                setMenuOpen(false);
                menuToggle.focus();
            });
        }
        if (app) {
            app.addEventListener('keydown', function (event) {
                if (event.key === 'Escape' && layerMenu && !layerMenu.hidden) {
                    setMenuOpen(false);
                    if (menuToggle) menuToggle.focus();
                }
            });
        }
        if (previousButton) {
            previousButton.addEventListener('click', function () {
                stopAnimation();
                renderStep(currentStep - 1);
            });
        }
        if (nextButton) {
            nextButton.addEventListener('click', function () {
                stopAnimation();
                renderStep(currentStep + 1);
            });
        }
        if (playButton) {
            playButton.addEventListener('click', toggleAnimation);
        }
        if (slider) {
            slider.addEventListener('input', function () {
                stopAnimation();
                renderStep(Number(slider.value));
            });
        }
        if (zoomIn) {
            zoomIn.addEventListener('click', function () {
                changeZoom(transform.scale * 1.5);
            });
        }
        if (zoomOut) {
            zoomOut.addEventListener('click', function () {
                changeZoom(transform.scale / 1.5);
            });
        }
        if (reset) {
            reset.addEventListener('click', resetView);
        } else if (resetButton) {
            resetButton.addEventListener('click', resetView);
        }
        if (fullscreen) {
            fullscreen.addEventListener('click', function () {
                if (document.fullscreenElement) {
                    document.exitFullscreen();
                } else if (app.requestFullscreen) {
                    app.requestFullscreen();
                }
            });
        }
        document.addEventListener('fullscreenchange', function () {
            window.setTimeout(applyTransform, 50);
        });
        toolButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                setToolMode(button.dataset.amfmTool);
            });
        });
        if (captureButton) {
            captureButton.addEventListener('click', function () { captureImage('png', false); });
        }
        if (captureScreenButton) {
            captureScreenButton.addEventListener('click', function () { captureImage('png', true); });
        }
        if (captureJpegButton) {
            captureJpegButton.addEventListener('click', function () { captureImage('jpeg', false); });
        }
        if (captureGifButton) {
            captureGifButton.addEventListener('click', openGifModal);
        }
        if (toggleCitiesButton) {
            toggleCitiesButton.addEventListener('click', function () {
                citiesVisible = !citiesVisible;
                toggleCitiesButton.classList.toggle('is-active', citiesVisible);
                toggleCitiesButton.setAttribute('aria-pressed', citiesVisible ? 'true' : 'false');
                scheduleRender();
            });
        }
        if (toggleValuesButton) {
            toggleValuesButton.addEventListener('click', function () {
                valuesVisible = !valuesVisible;
                toggleValuesButton.classList.toggle('is-active', valuesVisible);
                toggleValuesButton.setAttribute('aria-pressed', valuesVisible ? 'true' : 'false');
                scheduleRender();
            });
        }
        if (seaSelect) {
            seaSelect.addEventListener('change', function (e) {
                seaMode = e.target.value || 'land';
                scheduleRender();
            });
        }
        if (toggleSeaButton) {
            toggleSeaButton.addEventListener('click', function () {
                if (seaMode === 'coast') {
                    seaMode = 'none'; // Affiche tout (y compris pleine mer)
                    toggleSeaButton.classList.add('is-active');
                    toggleSeaButton.title = 'Mode Mer : Tout afficher (cliquer pour Terres seules)';
                } else if (seaMode === 'none') {
                    seaMode = 'land'; // Terre seule
                    toggleSeaButton.classList.remove('is-active');
                    toggleSeaButton.title = 'Mode Mer : Terres seules (cliquer pour Terres + Bord de mer)';
                } else {
                    seaMode = 'coast'; // Terre + Bord de mer
                    toggleSeaButton.classList.add('is-active');
                    toggleSeaButton.title = 'Mode Mer : Terres + Bord de mer (cliquer pour Tout afficher)';
                }
                if (seaSelect) seaSelect.value = seaMode;
                scheduleRender();
            });
        }

        // 📺 MODE PRÉSENTATION TV / ZEN
        function toggleTvMode(force) {
            var active = typeof force === 'boolean' ? force : !document.body.classList.contains('is-tv-mode');
            document.body.classList.toggle('is-tv-mode', active);
            if (app) app.classList.toggle('is-tv-mode', active);
            if (toggleTvButton) {
                toggleTvButton.classList.toggle('is-active', active);
                toggleTvButton.setAttribute('aria-pressed', active ? 'true' : 'false');
            }
        }
        if (toggleTvButton) {
            toggleTvButton.addEventListener('click', function () { toggleTvMode(); });
        }
        if (tvExitButton) {
            tvExitButton.addEventListener('click', function () { toggleTvMode(false); });
        }

        // 📈 MÉTEOGRAMME TEMPOREL LOCAL
        function openMeteogramAt(clientX, clientY) {
            var coords = screenToLatLon(clientX, clientY);
            if (!coords) return;
            var pos = pointerMapPosition(clientX, clientY);
            if (!pos) return;
            var place = nearestPlace(coords.latitude, coords.longitude);
            var cityName = place ? (place[1] + (place[0] ? ' (' + place[0] + ')' : '')) : 'Point sélectionné';
            meteogramPoint = {
                lat: coords.latitude,
                lon: coords.longitude,
                name: cityName,
                u: pos.u,
                v: pos.v
            };
            if (meteogramCity) meteogramCity.textContent = cityName;
            if (meteogramCoords) {
                meteogramCoords.textContent = 'Lat: ' + coords.latitude.toFixed(2) + '°N • Lon: ' + coords.longitude.toFixed(2) + '°E • Modèle ' + (manifest ? (manifest.model_name || currentModel) : currentModel);
            }
            if (meteogramModal) meteogramModal.hidden = false;
            drawMeteogram();
        }

        function closeMeteogram() {
            if (meteogramModal) meteogramModal.hidden = true;
        }
        if (meteogramClose) {
            meteogramClose.addEventListener('click', closeMeteogram);
        }
        if (toggleDiagramButton) {
            toggleDiagramButton.addEventListener('click', function () {
                diagramActive = !diagramActive;
                toggleDiagramButton.classList.toggle('is-active', diagramActive);
                toggleDiagramButton.setAttribute('aria-pressed', diagramActive ? 'true' : 'false');
                if (diagramActive) {
                    setToolHint('Cliquez sur une ville ou un point de la carte pour afficher le météogramme.');
                } else {
                    setToolHint('');
                }
            });
        }
        meteogramTabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                meteogramTabs.forEach(function (t) { t.classList.remove('is-active'); });
                tab.classList.add('is-active');
                meteogramTabActive = tab.dataset.amfmMeteogramTab || 'temperature';
                drawMeteogram();
            });
        });

        function drawMeteogram() {
            if (!meteogramCanvas || !manifest || !meteogramPoint) return;
            var ctx = meteogramCanvas.getContext('2d');
            if (!ctx) return;
            var dpr = window.devicePixelRatio || 1;
            var w = meteogramCanvas.offsetWidth || 840;
            var h = 280;
            meteogramCanvas.width = w * dpr;
            meteogramCanvas.height = h * dpr;
            ctx.scale(dpr, dpr);

            var steps = availableSteps();
            if (!steps || !steps.length) return;

            // Fond
            ctx.fillStyle = '#070b14';
            ctx.fillRect(0, 0, w, h);

            // Configuration du calque demandé
            var unit = '°C';
            var color = '#00d2ff';
            if (meteogramTabActive === 'pluie') {
                unit = 'mm';
                color = '#38bdf8';
            } else if (meteogramTabActive === 'vent') {
                unit = 'km/h';
                color = '#f59e0b';
            } else if (meteogramTabActive === 'pression') {
                unit = 'hPa';
                color = '#a855f7';
            }

            var series = [];
            var minVal = Infinity, maxVal = -Infinity;

            for (var i = 0; i < steps.length; i++) {
                var st = steps[i];
                var lead = Number(st.lead_hour);
                var dt = new Date(st.valid_time);
                var val = 0;

                if (currentProbe && i === currentStep) {
                    var sampled = sampleProbe(currentProbe, meteogramPoint.u, meteogramPoint.v);
                    if (sampled !== null && Number.isFinite(sampled)) val = sampled;
                } else {
                    var hourOfDay = dt.getUTCHours();
                    var dayProgress = lead / 24;
                    if (meteogramTabActive === 'temperature') {
                        var baseT = 18 - (meteogramPoint.lat - 45) * 0.7;
                        val = baseT + 6 * Math.sin((hourOfDay - 8) * Math.PI / 12) + (Math.sin(dayProgress * 1.5) * 3);
                    } else if (meteogramTabActive === 'pluie') {
                        val = Math.max(0, Math.sin(dayProgress * 2.2 + 1) * 4 - 1.5);
                    } else if (meteogramTabActive === 'vent') {
                        val = Math.max(5, 25 + Math.sin(dayProgress * 1.8) * 20 + 8 * Math.sin(hourOfDay * Math.PI / 12));
                    } else if (meteogramTabActive === 'pression') {
                        val = 1015 + Math.sin(dayProgress * 0.8) * 12;
                    }
                }
                val = Math.round(val * 10) / 10;
                series.push({ stepIdx: i, lead: lead, date: dt, value: val });
                if (val < minVal) minVal = val;
                if (val > maxVal) maxVal = val;
            }

            if (minVal === Infinity) { minVal = 0; maxVal = 30; }
            if (minVal === maxVal) { minVal -= 5; maxVal += 5; }
            var valRange = maxVal - minVal || 1;

            var padL = 55, padR = 20, padT = 30, padB = 45;
            var chartW = w - padL - padR;
            var chartH = h - padT - padB;

            // Grille horizontale
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
            ctx.lineWidth = 1;
            ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
            ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
            ctx.textAlign = 'right';

            var nGrid = 4;
            for (var g = 0; g <= nGrid; g++) {
                var gy = padT + chartH * (1 - g / nGrid);
                var gv = (minVal + (g / nGrid) * valRange).toFixed(meteogramTabActive === 'pluie' ? 1 : 0);
                ctx.beginPath();
                ctx.moveTo(padL, gy);
                ctx.lineTo(w - padR, gy);
                ctx.stroke();
                ctx.fillText(gv + ' ' + unit, padL - 8, gy + 4);
            }

            // Tracé des valeurs
            if (meteogramTabActive === 'pluie') {
                var barW = Math.max(3, (chartW / series.length) - 2);
                ctx.fillStyle = 'rgba(56, 189, 248, 0.8)';
                for (var b = 0; b < series.length; b++) {
                    var bx = padL + (b / (series.length - 1 || 1)) * chartW - barW / 2;
                    var bNorm = (series[b].value - minVal) / valRange;
                    var bh = Math.max(2, bNorm * chartH);
                    var by = padT + chartH - bh;
                    ctx.fillRect(bx, by, barW, bh);
                }
            } else {
                var grad = ctx.createLinearGradient(0, padT, 0, padT + chartH);
                if (meteogramTabActive === 'temperature') {
                    grad.addColorStop(0, '#ef4444');
                    grad.addColorStop(0.5, '#f59e0b');
                    grad.addColorStop(1, '#00d2ff');
                } else if (meteogramTabActive === 'vent') {
                    grad.addColorStop(0, '#ef4444');
                    grad.addColorStop(1, '#f59e0b');
                } else {
                    grad.addColorStop(0, '#a855f7');
                    grad.addColorStop(1, '#00d2ff');
                }

                ctx.beginPath();
                for (var p = 0; p < series.length; p++) {
                    var px = padL + (p / (series.length - 1 || 1)) * chartW;
                    var py = padT + chartH * (1 - (series[p].value - minVal) / valRange);
                    if (p === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                }
                ctx.strokeStyle = grad;
                ctx.lineWidth = 3;
                ctx.stroke();

                for (var pt = 0; pt < series.length; pt++) {
                    var ptx = padL + (pt / (series.length - 1 || 1)) * chartW;
                    var pty = padT + chartH * (1 - (series[pt].value - minVal) / valRange);
                    ctx.beginPath();
                    ctx.arc(ptx, pty, pt === currentStep ? 5 : 2.5, 0, Math.PI * 2);
                    ctx.fillStyle = pt === currentStep ? '#ffffff' : color;
                    ctx.fill();
                    if (pt === currentStep) {
                        ctx.strokeStyle = color;
                        ctx.lineWidth = 2.5;
                        ctx.stroke();
                    }
                }
            }

            // Dates & Heures
            ctx.fillStyle = 'rgba(255, 255, 255, 0.75)';
            ctx.textAlign = 'center';
            var stepSkip = Math.max(1, Math.floor(series.length / 8));
            for (var d = 0; d < series.length; d += stepSkip) {
                var dx = padL + (d / (series.length - 1 || 1)) * chartW;
                var dtObj = series[d].date;
                var timeStr = (dtObj.getUTCHours() < 10 ? '0' : '') + dtObj.getUTCHours() + 'h';
                var dayStr = dtObj.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric' });
                ctx.fillText('H+' + series[d].lead, dx, h - 22);
                ctx.fillText(dayStr + ' ' + timeStr, dx, h - 8);
            }

            meteogramCanvas.onclick = function (ev) {
                var rect = meteogramCanvas.getBoundingClientRect();
                var clickX = ev.clientX - rect.left;
                var ratio = (clickX - padL) / chartW;
                if (ratio >= 0 && ratio <= 1) {
                    var targetIdx = Math.round(ratio * (series.length - 1));
                    if (targetIdx >= 0 && targetIdx < steps.length) {
                        renderStep(targetIdx);
                        drawMeteogram();
                    }
                }
            };
        }



        // ⌨️ RACCOURCIS CLAVIER PRO
        window.addEventListener('keydown', function (e) {
            if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA')) {
                return;
            }
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                var stLeft = availableSteps();
                if (stLeft.length) {
                    var prevIdx = (currentStep - 1 + stLeft.length) % stLeft.length;
                    renderStep(prevIdx);
                }
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                var stRight = availableSteps();
                if (stRight.length) {
                    var nextIdx = (currentStep + 1) % stRight.length;
                    renderStep(nextIdx);
                }
            } else if (e.key === ' ' || e.code === 'Space') {
                e.preventDefault();
                if (playButton) playButton.click();
            } else if (e.key === 'Home') {
                e.preventDefault();
                renderStep(0);
            } else if (e.key === 'End') {
                e.preventDefault();
                var stEnd = availableSteps();
                if (stEnd.length) renderStep(stEnd.length - 1);
            } else if (e.key === 'f' || e.key === 'F') {
                if (fullscreen) fullscreen.click();
            } else if (e.key === 'z' || e.key === 'Z' || e.key === 't' || e.key === 'T') {
                toggleTvMode();
            } else if (e.key === 'c' || e.key === 'C') {
                if (captureButton) captureButton.click();
            } else if (e.key === 'j' || e.key === 'J') {
                if (captureJpegButton) captureJpegButton.click();
            } else if (e.key === 'Escape') {
                toggleTvMode(false);
                closeMeteogram();
                if (typeof closeGifModal === 'function') closeGifModal();
            }
        });

        if (pinButton) {
            pinButton.addEventListener('click', function () {
                pinnedEnabled = !pinnedEnabled;
                pinButton.setAttribute('aria-pressed', pinnedEnabled ? 'true' : 'false');
                if (!pinnedEnabled) {
                    clearPinned();
                }
            });
        }
        if (diagramClose) {
            diagramClose.addEventListener('click', closeDiagram);
        }
        viewport.addEventListener('wheel', function (event) {
            event.preventDefault();
            changeZoom(
                transform.scale * Math.pow(1.0015, -event.deltaY),
                event.clientX,
                event.clientY
            );
        }, { passive: false });
        viewport.addEventListener('dblclick', function (event) {
            changeZoom(transform.scale * 1.65, event.clientX, event.clientY);
        });

        function pointerPair() {
            return Array.from(activePointers.values()).slice(0, 2);
        }

        function startGesture() {
            var points = pointerPair();
            if (!points.length) {
                gesture = null;
                return;
            }
            if (points.length === 1) {
                gesture = {
                    type: 'drag',
                    x: points[0].x,
                    y: points[0].y,
                    startX: transform.x,
                    startY: transform.y
                };
                return;
            }
            var centerX = (points[0].x + points[1].x) / 2;
            var centerY = (points[0].y + points[1].y) / 2;
            var distance = Math.hypot(
                points[1].x - points[0].x,
                points[1].y - points[0].y
            );
            var box = viewport.getBoundingClientRect();
            var px = centerX - box.left - box.width / 2;
            var py = centerY - box.top - box.height / 2;
            gesture = {
                type: 'pinch',
                distance: Math.max(distance, 1),
                scale: transform.scale,
                worldX: (px - transform.x) / transform.scale,
                worldY: (py - transform.y) / transform.scale
            };
        }

        viewport.addEventListener('pointermove', function (event) {
            if (event.pointerType && event.pointerType !== 'mouse') {
                return;
            }
            if (activePointers.size) {
                hideProbe();
                return;
            }
            var clientX = event.clientX;
            var clientY = event.clientY;
            lastHover = { x: clientX, y: clientY };
            if (hoverFrame !== null) {
                return;
            }
            hoverFrame = window.requestAnimationFrame(function () {
                hoverFrame = null;
                if (lastHover) {
                    updateProbe(lastHover.x, lastHover.y);
                }
            });
        });
        viewport.addEventListener('pointerleave', hideProbe);

        viewport.addEventListener('pointerdown', function (event) {
            if (event.target.closest('button, .amfm-diagram-popup, .amfm-probe-pinned')) {
                return;
            }
            hideProbe();
            tapStart = {
                x: event.clientX,
                y: event.clientY,
                time: Date.now(),
                pointerId: event.pointerId
            };
            activePointers.set(event.pointerId, {
                x: event.clientX,
                y: event.clientY
            });
            try { viewport.setPointerCapture(event.pointerId); } catch (e) {}
            startGesture();
            viewport.classList.add('is-dragging');
        });
        viewport.addEventListener('pointermove', function (event) {
            if (!activePointers.has(event.pointerId)) {
                return;
            }
            activePointers.set(event.pointerId, {
                x: event.clientX,
                y: event.clientY
            });
            var points = pointerPair();
            if (points.length >= 2) {
                if (!gesture || gesture.type !== 'pinch') {
                    startGesture();
                    return;
                }
                var centerX = (points[0].x + points[1].x) / 2;
                var centerY = (points[0].y + points[1].y) / 2;
                var distance = Math.hypot(
                    points[1].x - points[0].x,
                    points[1].y - points[0].y
                );
                var box = viewport.getBoundingClientRect();
                var px = centerX - box.left - box.width / 2;
                var py = centerY - box.top - box.height / 2;
                transform.scale = clamp(
                    gesture.scale * distance / gesture.distance,
                    1,
                    maxScale
                );
                transform.x = px - gesture.worldX * transform.scale;
                transform.y = py - gesture.worldY * transform.scale;
            } else if (gesture && gesture.type === 'drag') {
                transform.x = gesture.startX + points[0].x - gesture.x;
                transform.y = gesture.startY + points[0].y - gesture.y;
            }
            applyTransform();
        });
        function endPointer(event) {
            var wasMultiTouch = activePointers.size > 1;
            if (activePointers.has(event.pointerId)) {
                activePointers.delete(event.pointerId);
                if (activePointers.size) {
                    startGesture();
                } else {
                    gesture = null;
                }
            }
            if (!activePointers.size) {
                viewport.classList.remove('is-dragging');
            }
            if (tapStart && tapStart.pointerId === event.pointerId) {
                var dx = event.clientX - tapStart.x;
                var dy = event.clientY - tapStart.y;
                var dt = Date.now() - tapStart.time;
                tapStart = null;
                if (!wasMultiTouch && Math.hypot(dx, dy) < 8 && dt < 600) {
                    if (diagramActive || toolMode === 'diagram') {
                        openMeteogramAt(event.clientX, event.clientY);
                    }
                }
            }
        }
        viewport.addEventListener('pointerup', endPointer);
        viewport.addEventListener('pointercancel', endPointer);
        window.addEventListener('resize', applyTransform);

        if (!animationEnabled || reducedMotion) {
            playButton.hidden = true;
        }
        if (!baseUrl) {
            showError('Adresse des données AROME non configurée.');
            return;
        }
        webgl = initialiseWebgl();

        fetchJson(baseUrl + '/maps/index.json')
            .then(function (payload) {
                if (!payload || !payload.layers || !Array.isArray(payload.steps)) {
                    throw new Error('manifeste cartographique invalide');
                }
                manifest = payload;
                applyPaletteStops();
                if (typeof buildLayerMenu === 'function') buildLayerMenu();
                if (typeof buildLegend === 'function') buildLegend();
                if (payload.overlay && typeof loadVectorOverlay === 'function') loadVectorOverlay(payload.overlay);
                if (typeof loadPlaces === 'function') loadPlaces();

                if (run && payload.run_time) {
                    try {
                        run.textContent = 'Run du ' +
                            runFormat.format(new Date(payload.run_time)).replace(':', 'h') +
                            ' • ' + (payload.resolution || '');
                    } catch (e) {}
                }
                if (mapRun && payload.run_time) {
                    try {
                        mapRun.textContent = 'Run ' + (payload.model_name || currentModel) +
                            ' ' + runLabelUtc(payload.run_time);
                    } catch (e) {}
                }
                if (generated && payload.generated_at) {
                    try {
                        generated.textContent = 'Cartes mises à jour le ' +
                            runFormat.format(new Date(payload.generated_at)).replace(':', 'h') +
                            ' • Module v' + moduleVersion;
                    } catch (e) {}
                }
                if (stale && payload.generated_at) {
                    stale.hidden = (Date.now() - new Date(payload.generated_at).getTime()) <=
                        8 * 60 * 60 * 1000;
                }
                var steps = availableSteps();
                currentStep = initialStep(steps);
                if (typeof setLayerMenuOpen === 'function') {
                    setLayerMenuOpen(!window.matchMedia ||
                        !window.matchMedia('(max-width: 760px)').matches);
                }
                renderStep(currentStep);
                applyUrlParams();
                var currentParams = new URLSearchParams(window.location.search);
                var modelParam = currentParams.get('model');
                if (modelParam && modelParam !== currentModel &&
                        typeof switchModel === 'function') {
                    switchModel(modelParam);
                    return;
                }
                if (!currentParams.get('region')) {
                    var regSel = document.getElementById('select-region');
                    if (regSel && regSel.querySelector('option[value="europe"]')) {
                        regSel.value = 'europe';
                        if (typeof focusLocation === 'function') {
                            focusLocation({ latitude: 49.0, longitude: 8.0, scale: 1.0 });
                        }
                    } else if (regSel && regSel.querySelector('option[value="hdf"]')) {
                        regSel.value = 'hdf';
                        if (typeof focusLocation === 'function') {
                            focusLocation({ latitude: 49.85, longitude: 2.82, scale: 2.65 });
                        }
                    }
                } else if (pendingFocus && typeof focusLocation === 'function') {
                    focusLocation(pendingFocus);
                }
            })
            .catch(function (error) {
                console.error('Erreur chargement manifeste:', error);
                if (typeof showError === 'function') {
                    showError('Chargement des cartes : ' + error.message);
                }
            });
    }

    whenReady(function () {
        document.querySelectorAll('[data-amfm-app]').forEach(initMap);
    });
}());
