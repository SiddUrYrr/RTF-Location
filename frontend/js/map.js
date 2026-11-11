/**
 * MapManager: Official Google Maps HD Tiles with Zoom Controls & Avatar Photos.
 */
class MapManager {
  constructor() {
    this.map = null;
    this.markers = {};
    this.myMarker = null;
    this.myCircle = null;
    this.historyPolyline = null;
    this.historyStartMarker = null;
    this.historyEndMarker = null;
  }

  async init() {
    const container = document.getElementById('mapCanvas');
    if (!container) return;

    if (this.map) {
      try { this.map.remove(); } catch (e) {}
      this.map = null;
      this.markers = {};
      this.myMarker = null;
    }
    if (container._leaflet_id) {
      container._leaflet_id = null;
    }

    this.map = L.map('mapCanvas', {
      zoomControl: false,
      attributionControl: false
    }).setView([28.6139, 77.2090], 15);

    // High-Resolution Google Maps Road & Landmark Layer (Exact view as requested)
    this.tileLayer = L.tileLayer('https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
      maxZoom: 20,
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
      attribution: '&copy; Google Maps'
    }).addTo(this.map);

    this.map.invalidateSize();
    setTimeout(() => {
      if (this.map) this.map.invalidateSize();
    }, 250);
  }

  // ZOOM IN & ZOOM OUT FUNCTIONS
  zoomIn() {
    if (this.map) this.map.zoomIn();
  }

  zoomOut() {
    if (this.map) this.map.zoomOut();
  }

  createAvatarIcon(name, avatarUrl = null, isMe = false, isSos = false, battery = null) {
    const initial = esc((name ? name[0] : 'U').toUpperCase());
    const batteryBadge = battery ? `<div class="member-battery-badge">${Number(battery)}%</div>` : '';
    const pinClass = isSos ? 'pin-avatar-bubble sos' : (isMe ? 'pin-avatar-bubble me' : 'pin-avatar-bubble');

    const innerContent = (avatarUrl && (avatarUrl.startsWith('http') || avatarUrl.startsWith('data:image')))
      ? `<img src="${safeUrl(avatarUrl)}" alt="${esc(name || 'Avatar')}" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">`
      : initial;

    return L.divIcon({
      className: 'custom-map-icon',
      html: `
        <div class="custom-map-pin">
          <div class="${pinClass}">
            ${innerContent}
            ${batteryBadge}
          </div>
          <div class="pin-point"></div>
        </div>
      `,
      iconSize: [44, 54],
      iconAnchor: [22, 54],
      popupAnchor: [0, -50]
    });
  }

  updateMyPosition(lat, lng, accuracy = 20) {
    if (!this.map) return;
    const latlng = [lat, lng];
    const name = app.currentUser?.full_name || 'You';
    const avatar = app.currentUser?.avatar_url;
    const isSos = Boolean(app.currentUser?.is_sos_active);
    const battery = locationTracker.batteryLevel;

    const myPopupHtml = `
      <div style="min-width: 160px; padding: 2px;">
        <h6 style="margin: 0; font-weight: 800; font-size: 14.5px;">${esc(name)} (You)</h6>
        <div style="font-size: 11.5px; color: #10b981; font-weight: 700; margin-top: 2px;"><i class="bi bi-broadcast me-1"></i>Live GPS Sharing</div>
        ${battery ? `<div style="font-size: 12px; margin-top: 4px; color: #94a3b8;"><i class="bi bi-battery-charging text-success me-1"></i>Battery: ${battery}%</div>` : ''}
        <button class="btn btn-sm btn-outline-primary w-100 mt-2 py-1 rounded-3" style="font-size: 11.5px;" onclick="app.viewLocationHistory(app.currentUser?.id, 'Your')">
          <i class="bi bi-clock-history me-1"></i>My Route History
        </button>
      </div>
    `;

    if (!this.myMarker) {
      this.myMarker = L.marker(latlng, {
        icon: this.createAvatarIcon(name, avatar, true, isSos, battery),
        zIndexOffset: 1000
      }).addTo(this.map).bindPopup(myPopupHtml);

      this.myCircle = L.circle(latlng, {
        radius: accuracy,
        color: isSos ? '#f43f5e' : '#10b981',
        weight: 1.5,
        fillColor: isSos ? '#f43f5e' : '#10b981',
        fillOpacity: 0.15
      }).addTo(this.map);

      this.map.setView(latlng, 16);
      this._myState = { name, avatar, isSos, battery };
    } else {
      // GPU accelerated transform - super fast, no DOM rebuild
      this.myMarker.setLatLng(latlng);
      this.myCircle.setLatLng(latlng);
      this.myCircle.setRadius(accuracy);

      const stateChanged = !this._myState ||
        this._myState.isSos !== isSos ||
        this._myState.avatar !== avatar ||
        this._myState.name !== name ||
        Math.abs((this._myState.battery || 0) - (battery || 0)) >= 5;

      if (stateChanged) {
        this.myMarker.setIcon(this.createAvatarIcon(name, avatar, true, isSos, battery));
        this.myMarker.setPopupContent(myPopupHtml);
        this.myCircle.setStyle({ color: isSos ? '#f43f5e' : '#10b981', fillColor: isSos ? '#f43f5e' : '#10b981' });
        this._myState = { name, avatar, isSos, battery };
      }
    }
  }

  updateFamilyMarkers(familyFeed) {
    if (!this.map) return;
    const activeUids = new Set();

    familyFeed.forEach(item => {
      if (!item.location || (!item.is_sharing && !item.is_sos)) return;

      const uid = item.user_id;
      activeUids.add(String(uid));
      const lat = item.location.latitude;
      const lng = item.location.longitude;
      const name = item.full_name;
      const avatarUrl = item.avatar_url;
      const isSos = Boolean(item.is_sos);
      const battery = item.location.battery_level;

      const latlng = [lat, lng];
      const popupHtml = `
        <div style="min-width: 175px; padding: 2px;">
          <h6 style="margin: 0; font-weight: 800; font-size: 14.5px;">${esc(item.full_name)}</h6>
          <div style="font-size: 11.5px; color: #94a3b8;">@${esc(item.username)}</div>
          ${isSos ? '<div style="background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; font-weight: 800; font-size: 11px; padding: 4px 8px; margin: 6px 0;"><i class="bi bi-exclamation-triangle-fill me-1"></i>SOS EMERGENCY!</div>' : ''}
          <div class="d-flex align-items-center justify-content-between mt-2 pt-1" style="font-size: 12px; border-top: 1px solid rgba(255,255,255,0.1);">
            <span><i class="bi bi-battery-charging text-success me-1"></i>${battery ? battery + '%' : 'N/A'}</span>
            ${item.distance_km !== null ? `<span class="fw-bold" style="color: #6366f1;">${item.distance_km} km away</span>` : ''}
          </div>
          <button class="btn btn-sm btn-outline-primary w-100 mt-2 py-1 rounded-3" style="font-size: 11.5px;" onclick="app.viewLocationHistory(${Number(uid)}, ${escAttr(name)})">
            <i class="bi bi-clock-history me-1"></i>View Route History
          </button>
        </div>
      `;

      if (!this.markers[uid]) {
        const marker = L.marker(latlng, {
          icon: this.createAvatarIcon(name, avatarUrl, false, isSos, battery)
        }).addTo(this.map).bindPopup(popupHtml);
        marker._state = { isSos, avatarUrl, battery, name };
        this.markers[uid] = marker;
      } else {
        const marker = this.markers[uid];
        marker.setLatLng(latlng);
        const changed = !marker._state ||
          marker._state.isSos !== isSos ||
          marker._state.avatarUrl !== avatarUrl ||
          marker._state.name !== name ||
          Math.abs((marker._state.battery || 0) - (battery || 0)) >= 5;

        if (changed) {
          marker.setIcon(this.createAvatarIcon(name, avatarUrl, false, isSos, battery));
          marker.setPopupContent(popupHtml);
          marker._state = { isSos, avatarUrl, battery, name };
        }
      }
    });

    // Remove any markers for users who turned off sharing or are no longer active
    Object.keys(this.markers).forEach(uid => {
      if (!activeUids.has(String(uid))) {
        if (this.markers[uid]) {
          this.markers[uid].remove();
          delete this.markers[uid];
        }
      }
    });
  }

  drawRouteHistory(points, userName) {
    if (!this.map || !points || points.length === 0) return;
    this.clearRouteHistory();

    const latlngs = points.map(p => [p.latitude, p.longitude]);

    // Draw glowing polyline
    this.historyPolyline = L.polyline(latlngs, {
      color: '#6366f1',
      weight: 5,
      opacity: 0.88,
      lineCap: 'round',
      lineJoin: 'round'
    }).addTo(this.map);

    // Trip Start Marker
    const startPoint = points[0];
    const startIcon = L.divIcon({
      className: 'route-start-icon',
      html: `
        <div style="background: #10b981; color: #fff; width: 26px; height: 26px; border-radius: 50%; border: 3px solid #fff; box-shadow: 0 4px 10px rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800;">
          A
        </div>
      `,
      iconSize: [26, 26],
      iconAnchor: [13, 13]
    });
    this.historyStartMarker = L.marker([startPoint.latitude, startPoint.longitude], { icon: startIcon })
      .addTo(this.map)
      .bindPopup(`<b>Start Point (A)</b><br><small class="text-muted">${esc(startPoint.timestamp || '')}</small>`);

    // Trip End / Latest Point Marker
    if (points.length > 1) {
      const endPoint = points[points.length - 1];
      const endIcon = L.divIcon({
        className: 'route-end-icon',
        html: `
          <div style="background: #f43f5e; color: #fff; width: 26px; height: 26px; border-radius: 50%; border: 3px solid #fff; box-shadow: 0 4px 10px rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800;">
            B
          </div>
        `,
        iconSize: [26, 26],
        iconAnchor: [13, 13]
      });
      this.historyEndMarker = L.marker([endPoint.latitude, endPoint.longitude], { icon: endIcon })
        .addTo(this.map)
        .bindPopup(`<b>Latest Point (B)</b><br><small class="text-muted">${esc(endPoint.timestamp || '')}</small>`);
    }

    // Zoom and pan to fit the entire route
    this.map.fitBounds(this.historyPolyline.getBounds(), { padding: [50, 50], maxZoom: 16 });
  }

  clearRouteHistory() {
    if (this.historyPolyline) {
      this.map.removeLayer(this.historyPolyline);
      this.historyPolyline = null;
    }
    if (this.historyStartMarker) {
      this.map.removeLayer(this.historyStartMarker);
      this.historyStartMarker = null;
    }
    if (this.historyEndMarker) {
      this.map.removeLayer(this.historyEndMarker);
      this.historyEndMarker = null;
    }
  }

  focusLocation(lat, lng) {
    if (this.map && lat && lng) {
      this.map.setView([lat, lng], 16, { animate: true });
    }
  }

  recenterOnMe() {
    if (locationTracker.currentPosition) {
      this.focusLocation(locationTracker.currentPosition.latitude, locationTracker.currentPosition.longitude);
    }
  }
}

const mapManager = new MapManager();