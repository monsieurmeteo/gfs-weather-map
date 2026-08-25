/**
 * Gestionnaire Multi-Modèles Météorologiques (AROME, HARMONIE, ECMWF, GFS, ICON)
 * Permet la comparaison instantanée et la génération de météogrammes haute fidélité
 */
const WeatherModels = {
    arome: {
        id: 'arome',
        name: 'AROME France 0,01°',
        provider: 'Météo-France',
        resolution: '1,3 km',
        frequency: '1 heure',
        range: '48h',
        badge: 'HAUTE RÉSOLUTION',
        description: 'Le modèle le plus fin sur la France, résout la convection, les brises et le relief.'
    },
    harmonie: {
        id: 'harmonie',
        name: 'HARMONIE HD 0,025°',
        provider: 'DMI / KNMI',
        resolution: '2,5 km',
        frequency: '1 heure',
        range: '48h',
        badge: 'EU MAILLAGE FIN',
        description: 'Modèle européen haute résolution très réputé pour les orages et la nébulosité.'
    },
    ecmwf: {
        id: 'ecmwf',
        name: 'ECMWF IFS (CEP)',
        provider: 'Centre Européen',
        resolution: '9 km',
        frequency: '1 heure',
        range: '48h à 10j',
        badge: 'RÉFÉRENCE MONDIALE',
        description: 'Le modèle mondial le plus précis pour les synoptiques et les centres d’action.'
    },
    icon: {
        id: 'icon',
        name: 'ICON-EU 0,06°',
        provider: 'DWD (Allemagne)',
        resolution: '7 km',
        frequency: '1 heure',
        range: '120h',
        badge: 'DWD EUROPE',
        description: 'Modèle dynamique allemand très performant sur les masses d’air continentales.'
    },
    gfs: {
        id: 'gfs',
        name: 'GFS 0,13°',
        provider: 'NOAA (USA)',
        resolution: '13 km',
        frequency: '1 heure',
        range: '384h',
        badge: 'NOAA GLOBAL',
        description: 'Modèle américain mondial mis à jour 4 fois par jour.'
    }
};

/**
 * Récupère les prévisions horaires multi-modèles pour un point GPS donné
 * via l'API ouverte Open-Meteo haute précision
 */
async function fetchMultiModelPointForecast(lat, lon) {
    const params = new URLSearchParams({
        latitude: lat.toFixed(4),
        longitude: lon.toFixed(4),
        hourly: 'temperature_2m,apparent_temperature,precipitation,rain,snowfall,wind_speed_10m,wind_gusts_10m,wind_direction_10m,surface_pressure,cloud_cover,relative_humidity_2m,cape',
        models: 'meteofrance_arome_france,knmi_seamless,ecmwf_ifs025,dwd_icon,gfs_seamless',
        forecast_days: '2',
        timezone: 'Europe/Paris'
    });

    try {
        const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`Erreur API Open-Meteo: ${response.status}`);
        }
        return await response.json();
    } catch (err) {
        console.warn('Impossible de charger le comparateur multi-modèles:', err);
        return null;
    }
}

window.WeatherModels = WeatherModels;
window.fetchMultiModelPointForecast = fetchMultiModelPointForecast;
