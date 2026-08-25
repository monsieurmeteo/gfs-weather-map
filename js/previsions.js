/* =========================================================================
 * Météo-Climat Pro — Prévisions AROME HD par commune (refonte UI v2)
 * -------------------------------------------------------------------------
 *  LOGIQUE DE DONNÉES CONSERVÉE À L'IDENTIQUE :
 *   - Recherche geo.api.gouv.fr, décodage binaire MCV2, interpolations,
 *     calculs météo, seuils orage/neige, échéances : AUCUNE MODIFICATION.
 *  REFONTE UI/UX : hero ville, cartes de synthèse premium, graphiques avec
 *   axes/tooltips/états vides, tableaux sticky, responsive complet.
 * ========================================================================= */
(function () {
    'use strict';

    /* ── Constantes (données — inchangées) ───────────────────────────── */
    var BASE = 'output/arome/maps';
    var COMMUNES_API = 'https://geo.api.gouv.fr/communes';
    var NAN_I16 = -32768;

    var DIRECTIONS = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSO','SO','OSO','O','ONO','NO','NNO'];

    var CONDITIONS = {
        0: { label: 'Indéterminé', icon: '•' },
        1: { label: 'Dégagé', icon: '☀️' },
        2: { label: 'Peu nuageux', icon: '🌤️' },
        3: { label: 'Nuageux', icon: '⛅' },
        4: { label: 'Couvert', icon: '☁️' },
        5: { label: 'Pluie', icon: '🌦️' },
        6: { label: 'Forte pluie', icon: '🌧️' },
        7: { label: 'Neige', icon: '❄️' },
        8: { label: 'Brouillard', icon: '🌫️' },
        9: { label: 'Très venteux', icon: '💨' }
    };
    var THUNDER_RISKS = {
        0: { label: 'Minimal', icon: '⚪' },
        1: { label: 'Faible', icon: '🟢' },
        2: { label: 'Modéré', icon: '🟡' },
        3: { label: 'Fort', icon: '🟠' },
        4: { label: 'Sévère', icon: '🔴' }
    };
    var STORM_TYPES = {
        0: 'Pas d’orage organisé', 1: 'Cellules isolées', 2: 'Multicellulaire',
        3: 'Ligne / MCS', 4: 'Convection très intense'
    };
    var SNOW_RISKS = {
        0: { label: 'Aucun', icon: '⚪' }, 1: { label: 'Faible', icon: '🟢' },
        2: { label: 'Modéré', icon: '🟡' }, 3: { label: 'Fort', icon: '🟠' },
        4: { label: 'Très fort', icon: '🔴' }
    };
    var SNOW_STICK = { 0: 'Aucune', 1: 'Faible', 2: 'Possible', 3: 'Probable' };
    var SNOW_PHASE = { 0: '—', 1: 'Pluie', 2: 'Pluie/neige', 3: 'Neige' };
    var HAZARD_RISKS = { 0: 'Faible', 1: 'Faible', 2: 'Modéré', 3: 'Fort' };

    /* ── Aide utilisateur (tooltips ⓘ) ───────────────────────────────── */
    var HELP = {
        mucape: 'MUCAPE : énergie potentielle de convection disponible. Plus la valeur est élevée, plus l’air est instable et propice aux orages.',
        reflectivite: 'Réflectivité : intensité des précipitations estimée par le modèle (en dBZ), comme un radar. Au-delà de 45 dBZ, pluie forte ou grêle possible.',
        cisaillement: 'Cisaillement : variation du vent entre le sol et 100 m. Un cisaillement fort favorise les orages organisés (lignes, supercellulaires).',
        rafale_max: 'Rafale max échéance : plus forte rafale de vent atteinte depuis le début du run jusqu’à cette échéance (maximum cumulé).',
        interpolation: 'Interpolation bilinéaire : la valeur affichée est calculée à la position exacte de la commune à partir des 4 points de grille AROME les plus proches (grille 0,01° ≈ 1,3 km).',
        arome: 'AROME 0,01° : modèle haute résolution de Météo-France, maille d’environ 1,3 km sur la France.',
        lcl: 'LCL : niveau de condensation par soulèvement. Altitude à laquelle une parcelle d’air devient saturée (base des nuages convectifs).',
        foudre: 'Score d’activité foudre estimé (0 à 100) à partir de la MUCAPE et de la réflectivité.',
        grele: 'Risque de grêle estimé à partir de la MUCAPE, de la réflectivité et du graupel.',
        cape: 'CAPE (MUCAPE) : énergie convective disponible. 0-500 J/kg : faible ; 500-1500 : modérée ; >1500 : forte.',
        tenue: 'Tenue de la neige au sol : capacité de la neige fraîche à se maintenir (dépend de la température du sol et de l’air).'
    };
    function helpIcon(key, text) {
        var span = el('span', 'help-ic', 'ⓘ');
        span.title = text || HELP[key] || '';
        span.setAttribute('role', 'img');
        span.setAttribute('aria-label', span.title);
        return span;
    }

    /* ── Helpers (inchangés) ─────────────────────────────────────────── */
    var $ = function (id) { return document.getElementById(id); };
    var el = function (tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined) e.textContent = text;
        return e;
    };
    function finite(v) { return typeof v === 'number' && Number.isFinite(v); }
    function fmt(v, d, suffix) {
        if (!finite(v)) return '—';
        return v.toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }) + (suffix || '');
    }
    function windDirection(deg) {
        if (!finite(deg)) return '';
        return DIRECTIONS[Math.round(deg / 22.5) % 16];
    }
    function tempClass(v) {
        if (!finite(v)) return '';
        if (v >= 35) return 'temp-hot';
        if (v >= 30) return 'temp-hot';
        if (v >= 25) return 'temp-warm';
        if (v >= 20) return 'temp-warm';
        if (v >= 10) return 'temp-mild';
        if (v >= 0) return 'temp-cool';
        return 'temp-cold';
    }
    function roundUp5(v) { return finite(v) ? Math.ceil(Math.max(0, Number(v)) / 5) * 5 : null; }
    function localDayKey(d) {
        var k = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        return k;
    }
    function dayLabel(d) {
        var wd = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'][d.getDay()];
        return wd + ' ' + d.getDate() + '/' + String(d.getMonth() + 1).padStart(2, '0');
    }
    function shortDayLabel(d) {
        var wd = ['dim.','lun.','mar.','mer.','jeu.','ven.','sam.'][d.getDay()];
        return wd + ' ' + d.getDate() + '/' + String(d.getMonth() + 1).padStart(2, '0');
    }
    function hourLabel(d) { return String(d.getHours()).padStart(2, '0') + 'h'; }

    /* ── État global ─────────────────────────────────────────────────── */
    var state = {
        index: null,
        deptCache: {},
        communes: [],
        colIndex: {},
        colScale: [], colOffset: [],
        leads: [],
        runTime: null,
        pointIdx: -1,
        city: null,
        debounce: null,
        searchCtrl: null
    };

    var ui = {
        input: $('mcp-input'), results: $('mcp-results'), locate: $('mcp-locate'),
        runbar: $('mcp-runbar'), run: $('mcp-run'), generated: $('mcp-generated'),
        error: $('mcp-error'), loading: $('mcp-loading'), main: $('mcp-main'),
        city: $('mcp-city'), cityMeta: $('mcp-city-meta'),
        summary: $('mcp-summary'),
        tblDaily: $('tbl-daily'), tblGeneral: $('tbl-general'),
        tblStorms: $('tbl-storms'), tblSnow: $('tbl-snow')
    };

    /* ── Réseau + décodage (INCHANGÉ) ────────────────────────────────── */
    function fetchJson(url, opts) {
        return fetch(url, opts).then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    }
    function showError(msg) {
        ui.error.textContent = msg;
        ui.error.style.display = 'block';
    }
    function clearError() { ui.error.style.display = 'none'; }
    function setLoading(on) {
        ui.loading.style.display = on ? 'block' : 'none';
        ui.main.style.display = on ? 'none' : 'block';
        if (!on) clearError();
    }

    function loadIndex() {
        return fetchJson(BASE + '/communes/index.json', { cache: 'no-cache' })
            .then(function (payload) {
                if (!payload || payload.format !== 'MCV2' || !payload.departments) {
                    throw new Error('Index des communes invalide (format MCV2 requis)');
                }
                state.index = payload;
                state.runTime = payload.run_time;
                state.leads = payload.leads || [];
                var runDate = new Date(payload.run_time);
                var runStr = runDate.toLocaleString('fr-FR', {
                    timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit',
                    hour: '2-digit', minute: '2-digit'
                }).replace(',', ' à');
                ui.run.textContent = 'Run du ' + runStr +
                    ' (' + (payload.run_time || '').slice(11, 16) + 'Z)';
                ui.generated.textContent = 'Mise à jour : ' +
                    new Date(payload.generated_at).toLocaleString('fr-FR', {
                        timeZone: 'Europe/Paris', day: '2-digit', month: '2-digit',
                        hour: '2-digit', minute: '2-digit'
                    });
                ui.runbar.style.display = 'flex';
                return payload;
            });
    }

    function gunzip(buf) {
        if (typeof DecompressionStream !== 'undefined') {
            return new Response(new Blob([buf]).stream()
                .pipeThrough(new DecompressionStream('deflate'))).arrayBuffer();
        }
        return Promise.reject(new Error(
            'Votre navigateur ne supporte pas la décompression native (DecompressionStream). ' +
            'Utilisez une version récente de Chrome, Firefox, Safari ou Edge.'));
    }

    function loadDepartment(dept) {
        if (state.deptCache[dept]) return Promise.resolve(state.deptCache[dept]);
        var url = BASE + '/communes/' + dept + '.bin.gz';
        return fetch(url, { cache: 'default' })
            .then(function (r) {
                if (!r.ok) throw new Error('Fichier département ' + dept + ' indisponible');
                return r.arrayBuffer();
            })
            .then(gunzip)
            .then(function (buf) { return decodeMCV2(buf); })
            .then(function (decoded) {
                state.deptCache[dept] = decoded;
                return decoded;
            });
    }

    function decodeMCV2(buf) {
        var dv = new DataView(buf);
        var magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
        if (magic !== 'MCV2') throw new Error('Format binaire inconnu : ' + magic);
        var n = dv.getUint16(4, true);
        var nleads = dv.getUint16(6, true);
        var ncols = dv.getUint16(8, true);
        var run = '';
        for (var i = 0; i < 40; i++) {
            var c = dv.getUint8(10 + i);
            if (c === 0) break;
            run += String.fromCharCode(c);
        }
        var off = 50;
        var communes = [];
        for (var k = 0; k < n; k++) {
            var code = '';
            for (var j = 0; j < 5; j++) {
                var cc = dv.getUint8(off + j);
                if (cc === 0) break;
                code += String.fromCharCode(cc);
            }
            off += 5;
            var nl = dv.getUint8(off); off += 1;
            var nom = '';
            for (var j2 = 0; j2 < nl; j2++) nom += String.fromCharCode(dv.getUint8(off + j2));
            off += nl;
            var lat = dv.getFloat32(off, true); off += 4;
            var lon = dv.getFloat32(off, true); off += 4;
            var pop = dv.getUint32(off, true); off += 4;
            communes.push({ code: code, nom: nom, lat: lat, lon: lon, pop: pop });
        }
        var colScale = [], colOffset = [], colNames = [];
        for (var j3 = 0; j3 < ncols; j3++) {
            var cname = '';
            for (var j4 = 0; j4 < 32; j4++) {
                var cc2 = dv.getUint8(off + j4);
                if (cc2 === 0) break;
                cname += String.fromCharCode(cc2);
            }
            off += 32;
            colScale.push(dv.getFloat32(off, true)); off += 4;
            colOffset.push(dv.getFloat32(off, true)); off += 4;
            colNames.push(cname);
        }
        var leads = [];
        for (var j5 = 0; j5 < nleads; j5++) { leads.push(dv.getUint16(off, true)); off += 2; }
        if (off % 2 !== 0) off += 1;
        var colIndex = {};
        colNames.forEach(function (nm, idx) { colIndex[nm] = idx; });
        var data = new Int16Array(buf, off, n * nleads * ncols);
        var shape = { n: n, nleads: nleads, ncols: ncols };
        return { communes: communes, leads: leads, colIndex: colIndex,
                 colScale: colScale, colOffset: colOffset, data: data, shape: shape, run: run };
    }

    function getValue(deptData, pointIdx, leadPos, colName) {
        var ci = deptData.colIndex[colName];
        if (ci === undefined) return null;
        var q = deptData.data[pointIdx * deptData.shape.nleads * deptData.shape.ncols
                             + leadPos * deptData.shape.ncols + ci];
        if (q === NAN_I16) return null;
        return q * deptData.colScale[ci] - deptData.colOffset[ci];
    }

    function valueAt(leadPos, colName) {
        return getValue(state.dept, state.pointIdx, leadPos, colName);
    }

    /* ── Recherche (inchangée) ───────────────────────────────────────── */
    function displayResults(candidates) {
        ui.results.replaceChildren();
        if (!candidates.length) { ui.results.classList.remove('open'); return; }
        candidates.forEach(function (cand) {
            var btn = el('button', 'mcp-result');
            btn.type = 'button';
            var left = el('span');
            left.style.display = 'flex';
            left.style.flexDirection = 'column';
            left.appendChild(el('span', 'r-name', cand.nom));
            left.appendChild(el('span', 'r-detail', ' ' + (cand.codesPostaux || []).join(', ') +
                ' • dépt ' + cand.codeDepartement +
                (cand.population ? ' • ' + Number(cand.population).toLocaleString('fr-FR') + ' hab.' : '')));
            btn.appendChild(left);
            btn.appendChild(el('span', 'r-detail', '📍'));
            btn.addEventListener('click', function () { selectCommune(cand); });
            ui.results.appendChild(btn);
        });
        ui.results.classList.add('open');
    }

    function searchCommunes(query) {
        if (state.searchCtrl) state.searchCtrl.abort();
        state.searchCtrl = new AbortController();
        var params = new URLSearchParams({
            fields: 'nom,code,codesPostaux,codeDepartement,population',
            format: 'json', boost: 'population', limit: '10'
        });
        if (/^\d{5}$/.test(query)) params.set('codePostal', query);
        else params.set('nom', query);
        fetchJson(COMMUNES_API + '?' + params.toString(), { signal: state.searchCtrl.signal })
            .then(function (payload) { displayResults(Array.isArray(payload) ? payload : []); })
            .catch(function (err) { if (err.name !== 'AbortError') displayResults([]); });
    }

    function selectCommune(cand) {
        ui.results.classList.remove('open');
        ui.input.value = cand.nom;
        state.city = cand;
        var dept = String(cand.codeDepartement || '').toUpperCase();
        if (!state.index || !state.index.departments[dept]) {
            showError('Ce département n’est pas couvert par les données AROME (métropole uniquement).');
            return;
        }
        setLoading(true);
        clearError();
        loadDepartment(dept)
            .then(function (deptData) {
                var idx = -1;
                for (var i = 0; i < deptData.communes.length; i++) {
                    if (deptData.communes[i].code === String(cand.code).padStart(5, '0') ||
                        deptData.communes[i].code === String(cand.code)) { idx = i; break; }
                }
                if (idx < 0) throw new Error('Commune absente du catalogue AROME : ' + cand.nom);
                state.pointIdx = idx;
                state.dept = deptData;
                renderForecast(deptData, idx, cand);
            })
            .catch(function (err) {
                setLoading(false);
                showError('Prévisions indisponibles : ' + err.message);
            });
    }

    /* ── Rendu principal ─────────────────────────────────────────────── */
    function renderForecast(deptData, idx, cand) {
        var nleads = deptData.shape.nleads;
        var forecasts = [];
        var now = Date.now() - 3600000;
        for (var lp = 0; lp < nleads; lp++) {
            var lh = deptData.leads[lp];
            var valid = new Date(new Date(state.runTime).getTime() + lh * 3600000);
            if (valid.getTime() < now) continue;
            forecasts.push({ lp: lp, lh: lh, valid: valid });
        }

        var tz = 'Europe/Paris';
        var hourFmt = new Intl.DateTimeFormat('fr-FR', { timeZone: tz, hour: '2-digit', minute: '2-digit' });
        var dayFmt = new Intl.DateTimeFormat('fr-FR', { timeZone: tz, weekday: 'long', day: '2-digit', month: '2-digit' });

        renderHero(cand, forecasts);
        renderSummary(forecasts);
        renderDailyTable(forecasts);
        renderGeneralTable(forecasts, hourFmt, dayFmt);
        renderStormsTable(forecasts, hourFmt, dayFmt);
        renderSnowTable(forecasts, hourFmt, dayFmt);

        setLoading(false);
    }

    /* ── Hero ville ──────────────────────────────────────────────────── */
    function renderHero(cand, forecasts) {
        var postal = (cand.codesPostaux && cand.codesPostaux.length) ? cand.codesPostaux[0] : '';
        ui.city.replaceChildren();
        ui.city.appendChild(el('span', null, cand.nom));
        if (postal) ui.city.appendChild(el('span', 'postal', postal));

        var alt = valueAt(0, 'altitude_m');
        var items = [
            { icon: 'fa-solid fa-location-dot', label: '📍', text: cand.nom + (postal ? ' — ' + postal : '') + ' · Département ' + cand.codeDepartement },
            { icon: 'fa-solid fa-mountain-sun', label: 'Altitude', text: finite(alt) ? Math.round(alt) + ' m' : '—' },
            { icon: 'fa-solid fa-microchip', label: 'Modèle', text: 'AROME 0,01°' + helpIcon('arome') },
            { icon: 'fa-solid fa-border-all', label: 'Résolution', text: '≈ 1,3 km' },
            { icon: 'fa-solid fa-clock', label: 'Échéances', text: forecasts.length + ' heures' },
            { icon: 'fa-solid fa-location-crosshairs', label: 'Précision', text: 'Interpolation bilinéaire' + helpIcon('interpolation') }
        ];
        ui.cityMeta.replaceChildren();
        items.forEach(function (it) {
            var item = el('div', 'mcp-hero-item');
            var ic = el('i', it.icon);
            ic.setAttribute('aria-hidden', 'true');
            item.appendChild(ic);
            var label = el('span', null, it.label + ' : ');
            var val = el('b', null);
            if (typeof it.text === 'string') val.textContent = it.text;
            else val.appendChild(it.text);
            item.appendChild(label);
            item.appendChild(val);
            ui.cityMeta.appendChild(item);
        });
    }

    /* ── Cartes de synthèse (Aperçu de la période) ───────────────────── */
    function renderSummary(forecasts) {
        var maxThunder = 0, maxSnow = 0, maxGust = 0, rainTotal = 0, snowTotal = 0;
        var tMin = null, tMax = null, gustAt = null, rainAt = null, snowAt = null;
        forecasts.forEach(function (f) {
            var th = valueAt(f.lp, 'thunder_risk_code');
            if (finite(th)) maxThunder = Math.max(maxThunder, Number(th));
            var sn = valueAt(f.lp, 'snow_risk_code');
            if (finite(sn)) maxSnow = Math.max(maxSnow, Number(sn));
            var g = valueAt(f.lp, 'wind_gust_max_kmh');
            if (finite(g) && Number(g) > maxGust) { maxGust = Number(g); gustAt = f.valid; }
            var r = valueAt(f.lp, 'precipitation_mm');
            if (finite(r)) rainTotal += Math.max(0, Number(r));
            var sf = valueAt(f.lp, 'snow_fresh_cm');
            if (finite(sf)) snowTotal += Math.max(0, Number(sf));
            var t = valueAt(f.lp, 'temperature_c');
            if (finite(t)) { tMin = tMin === null ? Number(t) : Math.min(tMin, Number(t)); tMax = tMax === null ? Number(t) : Math.max(tMax, Number(t)); }
        });

        ui.summary.replaceChildren();

        // Carte 1 — Risque orage
        ui.summary.appendChild(summaryCard({
            icon: '⛈️', label: 'Risque orage',
            html: riskPill(maxThunder, THUNDER_RISKS),
            sub: maxThunder === 0 ? 'Aucun signal orageux significatif' :
                'Maximum sur la période — MUCAPE + réflectivité' + helpIcon('mucape')
        }));

        // Carte 2 — Risque neige
        ui.summary.appendChild(summaryCard({
            icon: '❄️', label: 'Risque neige',
            html: riskPill(maxSnow, SNOW_RISKS),
            sub: maxSnow === 0 ? 'Aucune neige attendue' : 'Maximum sur la période'
        }));

        // Carte 3 — Rafale max
        ui.summary.appendChild(summaryCard({
            icon: '💨', label: 'Rafale maximale',
            value: maxGust > 0 ? String(Math.round(maxGust)) : null,
            unit: maxGust > 0 ? 'km/h' : '',
            sub: maxGust > 0
                ? (gustAt ? 'vers ' + hourLabel(gustAt) + ' · ' : '') + 'Maximum prévu sur la période' + helpIcon('rafale_max')
                : 'Donnée indisponible',
            valueClass: maxGust >= 100 ? 'temp-hot' : (maxGust >= 70 ? 'temp-warm' : '')
        }));

        // Carte 4 — Températures
        var amplitude = (tMin !== null && tMax !== null) ? Math.round(tMax - tMin) : null;
        ui.summary.appendChild(summaryCard({
            icon: '🌡️', label: 'Température',
            value: (tMin !== null ? Math.round(tMin) : '—') + '° → ' + (tMax !== null ? Math.round(tMax) : '—') + '°',
            sub: 'Min ' + (tMin !== null ? Math.round(tMin) + '°' : '—') +
                 ' · Max ' + (tMax !== null ? Math.round(tMax) + '°' : '—') +
                 (amplitude !== null ? ' · Amplitude ' + amplitude + '°' : '')
        }));

        // Carte 5 — Pluie cumulée
        ui.summary.appendChild(summaryCard({
            icon: '🌧️', label: 'Pluie cumulée',
            value: rainTotal > 0 ? fmt(rainTotal, 1) : (forecasts.length ? '0' : null),
            unit: rainTotal >= 0 ? 'mm' : '',
            sub: rainTotal === 0 ? 'Aucune pluie prévue sur la période' : 'Cumul sur la période'
        }));

        // Carte 6 — Neige fraîche
        ui.summary.appendChild(summaryCard({
            icon: '🌨️', label: 'Neige fraîche',
            value: snowTotal > 0 ? fmt(snowTotal, 1) : (forecasts.length ? '0' : null),
            unit: snowTotal >= 0 ? 'cm' : '',
            sub: snowTotal === 0 ? 'Aucune neige prévue' : 'Cumul sur la période'
        }));
    }

    function summaryCard(opt) {
        var card = el('div', 'mcp-sum-card');
        card.appendChild(el('span', 's-icon', opt.icon));
        card.appendChild(el('div', 's-label', opt.label));
        var val = el('div', 's-value' + (opt.valueClass ? ' ' + opt.valueClass : ''));
        if (opt.html) {
            val.style.fontSize = '16px';
            val.style.display = 'flex';
            val.style.alignItems = 'center';
            val.style.marginTop = '10px';
            val.appendChild(opt.html);
        } else if (opt.value !== null && opt.value !== undefined) {
            val.appendChild(document.createTextNode(opt.value));
            if (opt.unit) val.appendChild(el('span', 's-unit', opt.unit));
        } else {
            val.textContent = 'Donnée indisponible';
            val.style.fontSize = '18px';
            val.style.color = 'var(--text-3)';
        }
        card.appendChild(val);
        if (opt.sub) {
            var sub = el('div', 's-sub');
            if (typeof opt.sub === 'string') sub.textContent = opt.sub;
            else sub.appendChild(opt.sub);
            card.appendChild(sub);
        }
        return card;
    }

    function riskPill(code, table) {
        var r = table[Number(code)] || table[0];
        var pill = el('span', 'risk-pill risk-' + Number(code));
        pill.appendChild(el('span', null, r.label));
        return pill;
    }


    /* ══════════════════════════════════════════════════════════════════
       TABLEAUX
       ══════════════════════════════════════════════════════════════════ */

    /* Helper : cellule jour avec séparation propre et compteur explicite */
    function makeDayCell(d, count) {
        var td = el('td', 'mcp-day-cell');
        td.appendChild(document.createTextNode(dayLabel(d)));
        if (count > 1) {
            var cnt = el('span', 'day-count', '· ' + count + ' éch.');
            cnt.title = count + ' échéances horaires ce jour';
            td.appendChild(cnt);
        }
        return td;
    }

    /* ── Tableau journalier ──────────────────────────────────────────── */
    function renderDailyTable(forecasts) {
        var head = ['Jour', 'Temps', 'T min', 'T max', 'Pluie cumul.', 'Rafale max', 'Vent max',
                    'Risque orage', 'Risque neige', 'Neige fraîche'];
        var thead = ui.tblDaily.tHead || ui.tblDaily.createTHead();
        thead.replaceChildren();
        var tr = thead.insertRow();
        head.forEach(function (h) { tr.appendChild(el('th', null, h)); });
        var tbody = ui.tblDaily.createTBody();
        tbody.replaceChildren();

        var days = {};
        forecasts.forEach(function (f) {
            var k = localDayKey(f.valid);
            if (!days[k]) days[k] = { date: f.valid, items: [] };
            days[k].items.push(f);
        });

        Object.keys(days).forEach(function (k, di) {
            var day = days[k];
            var items = day.items;
            var row = tbody.insertRow();
            if (di > 0) row.classList.add('mcp-new-day');

            row.appendChild(makeDayCell(day.date, items.length));

            // Temps dominant
            var condCounts = {};
            items.forEach(function (f) {
                var cc = valueAt(f.lp, 'condition_code');
                var key = finite(cc) ? Number(cc) : 0;
                condCounts[key] = (condCounts[key] || 0) + 1;
            });
            var dominant = 0, dominantCount = 0;
            Object.keys(condCounts).forEach(function (cc) {
                if (condCounts[cc] > dominantCount) { dominant = Number(cc); dominantCount = condCounts[cc]; }
            });
            var cond = CONDITIONS[dominant] || CONDITIONS[0];
            var tdCond = el('td', 'mcp-condition');
            tdCond.textContent = cond.icon + ' ' + cond.label;
            tdCond.title = 'Condition dominante sur la journée';
            row.appendChild(tdCond);

            var tMin = null, tMax = null, rainDay = 0, gustMax = 0, windMax = 0;
            var thMax = 0, snMax = 0, snowFresh = 0;
            items.forEach(function (f) {
                var t = valueAt(f.lp, 'temperature_c');
                if (finite(t)) {
                    tMin = tMin === null ? Number(t) : Math.min(tMin, Number(t));
                    tMax = tMax === null ? Number(t) : Math.max(tMax, Number(t));
                }
                var r = valueAt(f.lp, 'precipitation_mm');
                if (finite(r)) rainDay += Math.max(0, Number(r));
                var g = valueAt(f.lp, 'wind_gust_max_kmh');
                if (finite(g)) gustMax = Math.max(gustMax, Number(g));
                var w = valueAt(f.lp, 'wind_speed_kmh');
                if (finite(w)) windMax = Math.max(windMax, Number(w));
                var th = valueAt(f.lp, 'thunder_risk_code');
                if (finite(th)) thMax = Math.max(thMax, Number(th));
                var sn = valueAt(f.lp, 'snow_risk_code');
                if (finite(sn)) snMax = Math.max(snMax, Number(sn));
                var sf = valueAt(f.lp, 'snow_fresh_cm');
                if (finite(sf)) snowFresh += Math.max(0, Number(sf));
            });

            var tdTmin = el('td', tMin !== null ? tempClass(tMin) : '');
            tdTmin.textContent = tMin !== null ? Math.round(tMin) + '°' : '—';
            row.appendChild(tdTmin);
            var tdTmax = el('td', tMax !== null ? tempClass(tMax) : '');
            tdTmax.textContent = tMax !== null ? Math.round(tMax) + '°' : '—';
            row.appendChild(tdTmax);

            var tdRain = el('td', rainDay >= 10 ? 'num-strong' : '');
            tdRain.textContent = rainDay > 0 ? fmt(rainDay, 1, ' mm') : (rainDay === 0 ? '0 mm' : '—');
            row.appendChild(tdRain);

            var tdGust = el('td', gustMax >= 100 ? 'num-strong' : (gustMax >= 70 ? 'temp-warm' : ''));
            tdGust.textContent = fmt(gustMax || null, 0, ' km/h');
            tdGust.title = 'Rafale max cumulée depuis le début du run';
            row.appendChild(tdGust);

            var tdWind = el('td');
            tdWind.textContent = fmt(windMax || null, 0, ' km/h');
            row.appendChild(tdWind);

            var tdTh = el('td');
            tdTh.appendChild(riskPill(thMax, THUNDER_RISKS));
            row.appendChild(tdTh);

            var tdSn = el('td');
            tdSn.appendChild(riskPill(snMax, SNOW_RISKS));
            row.appendChild(tdSn);

            var tdSnow = el('td');
            tdSnow.textContent = snowFresh > 0 ? fmt(snowFresh, 1, ' cm') : (snowFresh === 0 ? '0 cm' : '—');
            row.appendChild(tdSnow);
        });
    }

    /* ── Tableau général ─────────────────────────────────────────────── */
    function renderGeneralTable(forecasts, hourFmt, dayFmt) {
        var head = ['Jour', 'Heure', 'Temps', 'Temp.', 'Ressenti', 'Rosée', 'Humidité', 'Pluie 1h',
                    'Nuages', 'Vent', 'Rafales', 'Rafale max éch.', 'Pression'];
        var thead = ui.tblGeneral.tHead || ui.tblGeneral.createTHead();
        thead.replaceChildren();
        var tr = thead.insertRow();
        head.forEach(function (h) { tr.appendChild(el('th', null, h)); });
        var tbody = ui.tblGeneral.createTBody();
        tbody.replaceChildren();
        var dayCounts = {};
        forecasts.forEach(function (f) {
            var k = localDayKey(f.valid);
            dayCounts[k] = (dayCounts[k] || 0) + 1;
        });
        var prevDay = '';
        forecasts.forEach(function (f) {
            var row = tbody.insertRow();
            var k = localDayKey(f.valid);
            if (k !== prevDay) { row.classList.add('mcp-new-day'); prevDay = k; }
            row.appendChild(makeDayCell(f.valid, dayCounts[k]));
            row.appendChild(el('td', 'mcp-hour', hourFmt.format(f.valid)));

            var condCode = valueAt(f.lp, 'condition_code');
            var cond = CONDITIONS[Number(condCode)] || CONDITIONS[0];
            var tdCond = el('td', 'mcp-condition');
            tdCond.title = cond.label;
            tdCond.textContent = cond.icon + ' ' + cond.label;
            row.appendChild(tdCond);

            var t = valueAt(f.lp, 'temperature_c');
            var tdT = el('td');
            tdT.textContent = fmt(t, 0, '°');
            tdT.className = tempClass(t);
            row.appendChild(tdT);

            appendNum(row, valueAt(f.lp, 'wind_chill_c'), 0, '°');
            appendNum(row, valueAt(f.lp, 'dewpoint_c'), 1, '°');
            appendNum(row, valueAt(f.lp, 'humidity_pct'), 0, '%');
            var r = valueAt(f.lp, 'precipitation_mm');
            appendNum(row, r, 1, ' mm', finite(r) && r >= 5 ? 'num-strong' : '');
            appendNum(row, valueAt(f.lp, 'cloud_cover_pct'), 0, '%');

            // Vent : direction + valeur typographiée
            var w = roundUp5(valueAt(f.lp, 'wind_speed_kmh'));
            var tdW = el('td');
            var windBox = el('span', 'wind-cell');
            var dirDeg = valueAt(f.lp, 'wind_direction_deg');
            var dir = windDirection(dirDeg);
            if (dir) {
                var arrow = el('span', 'wind-arrow', '➜');
                arrow.style.transform = 'rotate(' + ((Number(dirDeg) + 180) % 360) + 'deg)';
                windBox.appendChild(arrow);
                windBox.appendChild(el('span', 'wind-dir', dir));
            }
            var strong = el('span', 'wind-speed', fmt(w, 0, ''));
            windBox.appendChild(strong);
            windBox.appendChild(el('span', 'wind-unit', 'km/h'));
            tdW.appendChild(windBox);
            row.appendChild(tdW);

            var g = roundUp5(valueAt(f.lp, 'wind_gust_kmh'));
            var tdG = el('td', finite(g) && g >= 80 ? 'num-strong' : '');
            tdG.textContent = fmt(g, 0, ' km/h');
            row.appendChild(tdG);

            var gm = valueAt(f.lp, 'wind_gust_max_kmh');
            var tdGm = el('td', finite(gm) && gm >= 100 ? 'num-strong' : (finite(gm) && gm >= 70 ? 'temp-warm' : ''));
            tdGm.textContent = fmt(gm, 0, ' km/h');
            tdGm.title = 'Rafale maximale cumulée depuis le début du run';
            row.appendChild(tdGm);

            appendNum(row, valueAt(f.lp, 'pressure_hpa'), 0, ' hPa');
        });
    }

    function appendNum(row, v, d, suffix, cls) {
        var td = el('td', cls || '');
        td.textContent = fmt(v, d, suffix);
        row.appendChild(td);
    }

    /* ── Tableau orages ──────────────────────────────────────────────── */
    function renderStormsTable(forecasts, hourFmt, dayFmt) {
        var head = ['Jour', 'Heure', 'Risque orage', 'CAPE', 'LCL', 'Foudre', 'Grêle', 'Pluie conv.',
                    'Graupel', 'Pluie 1h', 'Rafales', 'Type d’orage'];
        var thead = ui.tblStorms.tHead || ui.tblStorms.createTHead();
        thead.replaceChildren();
        var tr = thead.insertRow();
        head.forEach(function (h) { tr.appendChild(el('th', null, h)); });
        var tbody = ui.tblStorms.createTBody();
        tbody.replaceChildren();
        var dayCounts = {};
        forecasts.forEach(function (f) {
            var k = localDayKey(f.valid);
            dayCounts[k] = (dayCounts[k] || 0) + 1;
        });
        var prevDay = '';
        forecasts.forEach(function (f) {
            var row = tbody.insertRow();
            var k = localDayKey(f.valid);
            if (k !== prevDay) { row.classList.add('mcp-new-day'); prevDay = k; }
            row.appendChild(makeDayCell(f.valid, dayCounts[k]));
            row.appendChild(el('td', 'mcp-hour', hourFmt.format(f.valid)));

            var th = valueAt(f.lp, 'thunder_risk_code');
            var tdTh = el('td');
            tdTh.appendChild(riskPill(finite(th) ? th : 0, THUNDER_RISKS));
            row.appendChild(tdTh);

            var cape = valueAt(f.lp, 'cape_jkg');
            var tdCape = el('td', finite(cape) && cape >= 1500 ? 'num-strong' : (finite(cape) && cape >= 500 ? 'temp-warm' : ''));
            tdCape.textContent = finite(cape) && cape >= 25 ? fmt(cape, 0, ' J/kg') : '—';
            tdCape.appendChild(helpIcon('cape'));
            row.appendChild(tdCape);

            appendNum(row, valueAt(f.lp, 'lcl_m'), 0, ' m');
            var lig = valueAt(f.lp, 'lightning_score');
            appendNum(row, lig, 0, '/100', finite(lig) && lig >= 60 ? 'num-strong' : '');
            appendHazard(row, valueAt(f.lp, 'hail_risk_code'));
            appendNum(row, valueAt(f.lp, 'convective_precipitation_mm'), 1, ' mm');
            appendNum(row, valueAt(f.lp, 'graupel_mm'), 2, ' mm');
            var r = valueAt(f.lp, 'precipitation_mm');
            appendNum(row, r, 1, ' mm', finite(r) && r >= 5 ? 'num-strong' : '');
            var g = roundUp5(valueAt(f.lp, 'wind_gust_kmh'));
            appendNum(row, g, 0, ' km/h', finite(g) && g >= 80 ? 'num-strong' : '');

            var st = valueAt(f.lp, 'storm_type_code');
            row.appendChild(el('td', null, finite(st) ? (STORM_TYPES[Number(st)] || '—') : '—'));
        });
    }

    function appendHazard(row, code) {
        var td = el('td', finite(code) ? 'risk-pill risk-' + Number(code) : '');
        td.style.padding = '2px 8px';
        td.style.fontSize = '11px';
        td.textContent = finite(code) ? (HAZARD_RISKS[Number(code)] || '—') : '—';
        row.appendChild(td);
    }

    /* ── Tableau neige ───────────────────────────────────────────────── */
    function renderSnowTable(forecasts, hourFmt, dayFmt) {
        var head = ['Jour', 'Heure', 'Risque neige', 'Phase', 'Neige 1h', 'Neige 3h', 'Neige 6h',
                    'Tenue', 'Cumul fraîche', 'Pression', 'Humidité', 'Vent moyen / rafales'];
        var thead = ui.tblSnow.tHead || ui.tblSnow.createTHead();
        thead.replaceChildren();
        var tr = thead.insertRow();
        head.forEach(function (h) { tr.appendChild(el('th', null, h)); });
        var tbody = ui.tblSnow.createTBody();
        tbody.replaceChildren();
        var dayCounts = {};
        forecasts.forEach(function (f) {
            var k = localDayKey(f.valid);
            dayCounts[k] = (dayCounts[k] || 0) + 1;
        });
        var prevDay = '';
        forecasts.forEach(function (f, idx) {
            var row = tbody.insertRow();
            var k = localDayKey(f.valid);
            if (k !== prevDay) { row.classList.add('mcp-new-day'); prevDay = k; }
            row.appendChild(makeDayCell(f.valid, dayCounts[k]));
            row.appendChild(el('td', 'mcp-hour', hourFmt.format(f.valid)));

            var sn = valueAt(f.lp, 'snow_risk_code');
            var tdSn = el('td');
            tdSn.appendChild(riskPill(finite(sn) ? sn : 0, SNOW_RISKS));
            row.appendChild(tdSn);

            var ph = valueAt(f.lp, 'snow_phase_code');
            row.appendChild(el('td', null, finite(ph) ? (SNOW_PHASE[Number(ph)] || '—') : '—'));

            appendNum(row, valueAt(f.lp, 'snow_fresh_cm'), 1, ' cm');
            appendNum(row, snowSum(idx, 3), 1, ' cm');
            appendNum(row, snowSum(idx, 6), 1, ' cm');

            var stick = valueAt(f.lp, 'snow_stick_risk_code');
            var tdStick = el('td', finite(stick) ? 'risk-pill risk-' + Number(stick) : '');
            tdStick.style.padding = '2px 8px';
            tdStick.style.fontSize = '11px';
            tdStick.textContent = finite(stick) ? (SNOW_STICK[Number(stick)] || '—') : '—';
            tdStick.title = HELP.tenue;
            row.appendChild(tdStick);

            appendNum(row, valueAt(f.lp, 'snow_depth_cm'), 1, ' cm');
            appendNum(row, valueAt(f.lp, 'pressure_hpa'), 0, ' hPa');
            appendNum(row, valueAt(f.lp, 'humidity_pct'), 0, '%');

            var w = roundUp5(valueAt(f.lp, 'wind_speed_kmh'));
            var g = roundUp5(valueAt(f.lp, 'wind_gust_kmh'));
            var tdW = el('td');
            tdW.textContent = fmt(w, 0, '') + ' / ' + fmt(g, 0, '') + ' km/h';
            row.appendChild(tdW);
        });

        function snowSum(startIdx, windowHours) {
            var total = 0, found = false;
            for (var off = 0; off < windowHours && startIdx + off < forecasts.length; off++) {
                var v = valueAt(forecasts[startIdx + off].lp, 'snow_fresh_cm');
                if (finite(v)) { total += Number(v); found = true; }
            }
            return found ? total : null;
        }
    }

    /* ── Géolocalisation (inchangée) ─────────────────────────────────── */
    function detectCurrentCommune() {
        if (!navigator.geolocation) { showError('La géolocalisation n’est pas disponible.'); return; }
        ui.locate.disabled = true;
        ui.locate.classList.add('is-loading');
        ui.locate.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> Localisation…';
        navigator.geolocation.getCurrentPosition(function (pos) {
            var params = new URLSearchParams({
                lat: String(pos.coords.latitude), lon: String(pos.coords.longitude),
                fields: 'nom,code,codesPostaux,codeDepartement,population', format: 'json'
            });
            fetchJson(COMMUNES_API + '?' + params.toString(), { cache: 'default' })
                .then(function (payload) {
                    var candidates = Array.isArray(payload) ? payload : (payload ? [payload] : []);
                    var cand = candidates.find(function (c) {
                        return state.index && state.index.departments[String(c.codeDepartement).toUpperCase()];
                    });
                    if (!cand) throw new Error('position hors couverture AROME');
                    selectCommune(cand);
                })
                .catch(function (err) { showError('Impossible de détecter votre commune : ' + err.message); })
                .finally(function () {
                    ui.locate.disabled = false;
                    ui.locate.classList.remove('is-loading');
                    ui.locate.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> Me localiser';
                });
        }, function () {
            showError('Localisation refusée ou indisponible.');
            ui.locate.disabled = false;
            ui.locate.classList.remove('is-loading');
            ui.locate.innerHTML = '<i class="fa-solid fa-location-crosshairs"></i> Me localiser';
        }, { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
    }

    /* ── Onglets (avec aria + scroll horizontal) ─────────────────────── */
    function bindTabs() {
        document.querySelectorAll('.mcp-tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                document.querySelectorAll('.mcp-tab').forEach(function (t) {
                    t.classList.remove('active');
                    t.setAttribute('aria-selected', 'false');
                });
                document.querySelectorAll('.mcp-panel').forEach(function (p) { p.classList.remove('active'); });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');
                var panel = $('panel-' + tab.dataset.panel);
                if (panel) panel.classList.add('active');
            });
        });
    }

    /* ── Init (inchangé) ─────────────────────────────────────────────── */
    function init() {
        bindTabs();
        ui.locate.addEventListener('click', detectCurrentCommune);
        ui.input.addEventListener('input', function () {
            window.clearTimeout(state.debounce);
            var q = ui.input.value.trim();
            if (q.length < 2) { ui.results.classList.remove('open'); return; }
            if (/^\d+$/.test(q) && q.length < 5) { ui.results.classList.remove('open'); return; }
            state.debounce = window.setTimeout(function () { searchCommunes(q); }, 280);
        });
        ui.input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') ui.results.classList.remove('open');
        });
        document.addEventListener('click', function (e) {
            if (!e.target.closest('.mcp-search-wrap')) ui.results.classList.remove('open');
        });

        setLoading(true);
        loadIndex()
            .then(function () {
                var params = new URLSearchParams(location.search);
                var code = params.get('commune');
                if (code) {
                    var dept = String(code).slice(0, 2).toUpperCase();
                    return loadDepartment(dept).then(function (deptData) {
                        var idx = -1;
                        for (var i = 0; i < deptData.communes.length; i++) {
                            if (deptData.communes[i].code === String(code).padStart(5, '0') ||
                                deptData.communes[i].code === String(code)) { idx = i; break; }
                        }
                        if (idx < 0) throw new Error('Commune ' + code + ' introuvable');
                        var c = deptData.communes[idx];
                        state.city = { nom: c.nom, code: c.code, codesPostaux: [], codeDepartement: dept, population: c.pop };
                        state.pointIdx = idx;
                        state.dept = deptData;
                        ui.input.value = c.nom;
                        renderForecast(deptData, idx, { nom: c.nom, codesPostaux: [], codeDepartement: dept, population: c.pop });
                    });
                }
                return loadDepartment('75').then(function (deptData) {
                    var idx = 0;
                    for (var i = 0; i < deptData.communes.length; i++) {
                        if (deptData.communes[i].code === '75056') { idx = i; break; }
                    }
                    var c = deptData.communes[idx];
                    state.city = { nom: c.nom, code: c.code, codesPostaux: [], codeDepartement: '75', population: c.pop };
                    state.pointIdx = idx;
                    state.dept = deptData;
                    ui.input.value = c.nom;
                    renderForecast(deptData, idx, { nom: c.nom, codesPostaux: [], codeDepartement: '75', population: c.pop });
                });
            })
            .catch(function (err) {
                setLoading(false);
                showError('Données indisponibles : ' + err.message +
                    '. Les prévisions par commune seront actives après le prochain run AROME (pipeline v2).');
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
