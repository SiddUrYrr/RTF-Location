/**
 * App: Handles Profile, Photo Compression, Navbar buttons & live tracking.
 */
class App {
  constructor() {
    this.token = localStorage.getItem('token');
    this.currentUser = null;
    this.feedPollingInterval = null;
    this.mapInitialized = false;
    this.pendingAvatarBase64 = null;
    this.currentHistoryUserId = null;
    this.currentHistoryUserName = null;
    this.currentHistoryHours = 24;
  }

  async init() {
    this.applyTheme(localStorage.getItem('theme') || 'dark');
    this.initMobileGestures();
    this.initTabListeners();

    if (this.token) {
      await this.loadCurrentUser();
    } else {
      this.showAuthScreen();
    }
  }

  initTabListeners() {
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(tabBtn => {
      tabBtn.addEventListener('shown.bs.tab', (e) => {
        const target = e.target.getAttribute('data-bs-target');
        if (target === '#tabGroups') this.loadGroups();
        else if (target === '#tabRequests') this.loadRequests();
        else if (target === '#tabFamily') this.loadFamilyFeed();
      });
    });
  }

  showAuthScreen() {
    window.location.href = '/login';
  }

  async showDashboardScreen() {
    const authEl = document.getElementById('authScreen');
    const dashEl = document.getElementById('mainDashboard');
    if (authEl) authEl.classList.add('d-none');
    if (dashEl) {
      dashEl.classList.remove('d-none');
      dashEl.classList.add('d-flex');
    }

    if (!this.mapInitialized) {
      try {
        await mapManager.init();
      } catch (err) {
        console.error('Map init warning:', err);
      }
      try {
        locationTracker.startTracking();
      } catch (err) {
        console.error('Tracking init warning:', err);
      }
      this.mapInitialized = true;
    }
    setTimeout(() => {
      if (window.mapManager && mapManager.map && mapManager.map.invalidateSize) {
        mapManager.map.invalidateSize();
      }
    }, 250);
  }

  showLoginForm() {
    document.getElementById('loginForm').classList.remove('d-none');
    document.getElementById('signupForm').classList.add('d-none');
    document.getElementById('tabLoginBtn').classList.add('active');
    document.getElementById('tabSignupBtn').classList.remove('active');
  }

  showSignupForm() {
    document.getElementById('loginForm').classList.add('d-none');
    document.getElementById('signupForm').classList.remove('d-none');
    document.getElementById('tabLoginBtn').classList.remove('active');
    document.getElementById('tabSignupBtn').classList.add('active');
  }

  authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (this.token) {
      options.headers['Authorization'] = `Bearer ${this.token}`;
    }
    return fetch(url, options);
  }

  startFeedPolling() {
    if (this.feedPollingInterval) clearInterval(this.feedPollingInterval);
    this.feedPollingInterval = setInterval(() => {
      if (this.token && !document.hidden) {
        this.loadFamilyFeed();
        this.loadNotifications();
        this.loadRequests();
      }
    }, 8000);
  }

  async loadNotifications() {
    if (!this.token) return;
    try {
      const res = await this.authFetch('/api/notifications/');
      if (!res.ok) return;
      const notifs = await res.json();
      const notifList = document.getElementById('notificationList');
      if (notifList) {
        const hash = JSON.stringify(notifs);
        if (this._lastNotifHash === hash) return;
        this._lastNotifHash = hash;

        if (!notifs || notifs.length === 0) {
          notifList.innerHTML = '<div class="text-muted small text-center py-2">No new notifications</div>';
        } else {
          notifList.innerHTML = notifs.map(n => `
            <div class="notification-item p-2 border-bottom">
              <div class="fw-bold small">${esc(n.title)}</div>
              <div class="text-muted small">${esc(n.message)}</div>
            </div>
          `).join('');
        }
      }
    } catch (e) {
      console.warn('Could not load notifications:', e);
    }
  }

  async loadCurrentUser() {
    let res;
    try {
      res = await this.authFetch('/api/auth/me');
    } catch (e) {
      console.error('Network error during auth check:', e);
      return;
    }

    if (!res || !res.ok) {
      this.logout();
      return;
    }

    try {
      this.currentUser = await res.json();
    } catch (e) {
      console.error('User data parsing error:', e);
      this.logout();
      return;
    }

    // Authenticated! Show dashboard first
    await this.showDashboardScreen();
    this.renderUserData();
    this.updateSosUI();
    this.startFeedPolling();

    // Async secondary loads (never throw or hide dashboard)
    this.loadFamilyFeed().catch(e => console.warn('Family feed:', e));
    this.loadNotifications().catch(e => console.warn('Notifications:', e));
    this.loadGroups().catch(e => console.warn('Groups:', e));
    this.loadRequests().catch(e => console.warn('Requests:', e));
  }

  renderUserData() {
    if (!this.currentUser) return;
    const nameEl = document.getElementById('navUserName');
    if (nameEl) nameEl.innerText = this.currentUser.full_name;

    const navImg = document.getElementById('navUserAvatar');
    const navIcon = document.getElementById('navDefaultAvatarIcon');
    if (this.currentUser.avatar_url) {
      if (navImg) {
        navImg.src = this.currentUser.avatar_url;
        navImg.classList.remove('d-none');
      }
      if (navIcon) navIcon.classList.add('d-none');
    } else {
      if (navImg) navImg.classList.add('d-none');
      if (navIcon) navIcon.classList.remove('d-none');
    }

    const masterSwitch = document.getElementById('masterSharingSwitch');
    if (masterSwitch) masterSwitch.checked = Boolean(this.currentUser.is_sharing);
  }

  // Toggles the glowing "I AM SAFE NOW" button in the top bar
  updateSosUI() {
    const btnContainer = document.getElementById('navSafeBtnContainer');
    if (!btnContainer) return;
    if (this.currentUser?.is_sos_active) {
      btnContainer.classList.remove('d-none');
    } else {
      btnContainer.classList.add('d-none');
    }
  }

  openProfileModal() {
    if (!this.currentUser) return;
    document.getElementById('profFullName').value = this.currentUser.full_name || '';
    document.getElementById('profPhone').value = this.currentUser.phone || '';
    document.getElementById('profBio').value = this.currentUser.profile?.bio || '';
    document.getElementById('profAddress').value = this.currentUser.profile?.home_address || '';
    document.getElementById('profBloodGroup').value = this.currentUser.profile?.blood_group || '';
    document.getElementById('profMedicalNotes').value = this.currentUser.profile?.medical_notes || '';

    const previewImg = document.getElementById('profileModalAvatarPreview');
    const placeholder = document.getElementById('profileModalAvatarPlaceholder');
    const removeBtn = document.getElementById('btnRemoveAvatarPhoto');
    placeholder.innerText = (this.currentUser.full_name[0] || 'U').toUpperCase();

    if (this.currentUser.avatar_url) {
      previewImg.src = this.currentUser.avatar_url;
      previewImg.classList.remove('d-none');
      placeholder.classList.add('d-none');
      if (removeBtn) removeBtn.classList.remove('d-none');
    } else {
      previewImg.classList.add('d-none');
      placeholder.classList.remove('d-none');
      if (removeBtn) removeBtn.classList.add('d-none');
    }

    this.pendingAvatarBase64 = null;
    this.checkCloudinaryStatus();
    new bootstrap.Modal(document.getElementById('profileModal')).show();
  }

  async checkCloudinaryStatus() {
    const badgeEl = document.getElementById('cloudinaryStatusBadge');
    if (!badgeEl) return;
    try {
      const res = await fetch('/api/auth/cloudinary-status');
      if (res.ok) {
        const data = await res.json();
        if (data.connected) {
          badgeEl.innerHTML = `<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25 px-2 py-1"><i class="bi bi-cloud-check-fill me-1"></i>Cloudinary CDN Connected (${esc(data.cloud_name)})</span>`;
        } else if (data.configured) {
          badgeEl.innerHTML = `<span class="badge bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25 px-2 py-1" title="${escAttr(data.message)}"><i class="bi bi-exclamation-triangle-fill me-1"></i>Cloudinary Connection Error</span>`;
        } else {
          badgeEl.innerHTML = `<span class="badge bg-secondary bg-opacity-10 text-secondary border px-2 py-1" title="To enable Cloudinary CDN, set CLOUDINARY_URL or credentials in .env"><i class="bi bi-cloud-slash me-1"></i>Cloudinary: Not Configured (.env)</span>`;
        }
      }
    } catch (e) {
      console.warn('Could not check Cloudinary status:', e);
    }
  }

  handleAvatarFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const maxDim = 600;
        let width = img.width;
        let height = img.height;
        if (width > height) {
          if (width > maxDim) { height *= maxDim / width; width = maxDim; }
        } else {
          if (height > maxDim) { width *= maxDim / height; height = maxDim; }
        }
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        
        const compressedBase64 = canvas.toDataURL('image/jpeg', 0.90);
        this.pendingAvatarBase64 = compressedBase64;

        const previewImg = document.getElementById('profileModalAvatarPreview');
        const placeholder = document.getElementById('profileModalAvatarPlaceholder');
        const removeBtn = document.getElementById('btnRemoveAvatarPhoto');
        previewImg.src = compressedBase64;
        previewImg.classList.remove('d-none');
        placeholder.classList.add('d-none');
        if (removeBtn) removeBtn.classList.remove('d-none');
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  removeAvatarPhoto() {
    this.pendingAvatarBase64 = '__REMOVE__';
    const previewImg = document.getElementById('profileModalAvatarPreview');
    const placeholder = document.getElementById('profileModalAvatarPlaceholder');
    const removeBtn = document.getElementById('btnRemoveAvatarPhoto');
    if (previewImg) {
      previewImg.src = '';
      previewImg.classList.add('d-none');
    }
    if (placeholder) {
      placeholder.classList.remove('d-none');
    }
    if (removeBtn) {
      removeBtn.classList.add('d-none');
    }
    const fileInput = document.getElementById('avatarFileInput');
    if (fileInput) fileInput.value = '';
  }

  async handleProfileUpdate(event) {
    event.preventDefault();
    const saveBtn = document.getElementById('btnSaveProfile');
    const originalText = saveBtn ? saveBtn.innerHTML : 'Save Profile';

    const payload = {
      full_name: document.getElementById('profFullName').value.trim(),
      phone: document.getElementById('profPhone').value.trim() || null,
      bio: document.getElementById('profBio').value.trim() || null,
      home_address: document.getElementById('profAddress').value.trim() || null,
      blood_group: document.getElementById('profBloodGroup').value || null,
      medical_notes: document.getElementById('profMedicalNotes').value.trim() || null
    };

    if (this.pendingAvatarBase64) {
      payload.avatar_url = this.pendingAvatarBase64 === '__REMOVE__' ? '' : this.pendingAvatarBase64;
      if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = this.pendingAvatarBase64 === '__REMOVE__'
          ? '<span class="spinner-border spinner-border-sm me-2"></span>Removing Avatar...'
          : '<span class="spinner-border spinner-border-sm me-2"></span>Uploading to Cloudinary CDN...';
      }
    } else if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Saving...';
    }

    try {
      const res = await this.authFetch('/api/auth/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        this.currentUser = await res.json();
        this.renderUserData();
        if (this.mapHelper && typeof this.mapHelper.updateMyMarker === 'function') {
          this.mapHelper.updateMyMarker();
        }
        bootstrap.Modal.getInstance(document.getElementById('profileModal')).hide();
        alert('Profile & Photo updated successfully! 🎉');
      } else {
        const err = await res.json().catch(() => ({}));
        alert('Failed to update profile: ' + (err.detail || 'Unknown error'));
      }
    } catch (e) {
      alert('Error updating profile: ' + e.message);
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
      }
    }
  }

  async handleLogin(event) {
    event.preventDefault();
    const u = document.getElementById('loginUsername').value.trim();
    const p = document.getElementById('loginPassword').value;

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username_or_email: u, password: p })
      });

      if (res.ok) {
        const data = await res.json();
        this.token = data.access_token;
        localStorage.setItem('token', this.token);
        await this.loadCurrentUser();
      } else {
        const err = await res.json().catch(() => ({ detail: 'Invalid credentials' }));
        alert('Login Failed: ' + (err.detail || 'Invalid username or password'));
      }
    } catch (err) {
      alert('Connection error: ' + err.message);
    }
  }

  async handleSignup(event) {
    event.preventDefault();
    const fullName = document.getElementById('regFullName').value.trim();
    const email = document.getElementById('regEmail').value.trim();
    const password = document.getElementById('regPassword').value;

    // Direct registration with original email format validation
    const baseUsername = email.split('@')[0].replace(/[^a-zA-Z0-9_]/g, '').slice(0, 30) || ('user_' + Math.floor(Math.random() * 1000));
    const payload = {
      full_name: fullName,
      username: baseUsername,
      email: email,
      password: password
    };

    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        this.token = data.access_token;
        localStorage.setItem('token', this.token);
        await this.loadCurrentUser();
      } else {
        const err = await res.json().catch(() => ({ detail: 'Signup failed' }));
        alert('Signup Failed: ' + (err.detail || 'Check inputs. Original email required.'));
      }
    } catch (err) {
      alert('Signup connection error: ' + err.message);
    }
  }

  logout() {
    localStorage.removeItem('token');
    this.token = null;
    this.currentUser = null;
    if (this.feedPollingInterval) clearInterval(this.feedPollingInterval);
    if (window.locationTracker) locationTracker.stopTracking();
    window.location.href = '/login';
  }

  async handleSharingSwitch(isSharing) {
    if (!this.token) return;
    const res = await this.authFetch('/api/locations/toggle-sharing', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_sharing: isSharing })
    });
    if (res.ok) {
      const data = await res.json();
      this.currentUser.is_sharing = data.is_sharing;
      this.renderUserData();
    }
  }

  async loadFamilyFeed() {
    if (!this.token) return;
    try {
      const res = await this.authFetch('/api/locations/live-feed');
      if (!res.ok) return;
      const feed = await res.json();
      mapManager.updateFamilyMarkers(feed);

      const activeBadge = document.getElementById('sheetActiveCountBadge');
      if (activeBadge) {
        const liveCount = feed.filter(f => f.is_sharing || f.is_sos).length;
        activeBadge.innerText = `${liveCount} Live`;
      }

      const list = document.getElementById('familyList');
      if (!list) return;

      const feedHash = JSON.stringify(feed);
      if (this._lastFeedHash === feedHash) return;
      this._lastFeedHash = feedHash;

      if (feed.length === 0) {
        list.innerHTML = `<div class="text-center text-muted small py-3">No family members connected yet.</div>`;
        return;
      }

      list.innerHTML = feed.map(item => {
        const hasLoc = Boolean(item.location && item.location.latitude);
        const name = String(item.full_name || 'Unknown');
        const avatarContent = item.avatar_url
          ? `<img src="${safeUrl(item.avatar_url)}" alt="${esc(name)}">`
          : esc(name[0] ? name[0].toUpperCase() : '?');

        const batteryVal = item.location?.battery_level;
        let batteryColor = '#10b981';
        if (batteryVal !== null && batteryVal !== undefined) {
          if (batteryVal < 20) batteryColor = '#ef4444';
          else if (batteryVal < 45) batteryColor = '#f59e0b';
        }

        const batteryBadge = (batteryVal !== null && batteryVal !== undefined)
          ? `<div class="member-battery-badge" style="color: ${batteryColor};"><i class="bi bi-lightning-fill"></i>${batteryVal}%</div>`
          : '';

        const clickHandler = hasLoc
          ? `mapManager.focusLocation(${Number(item.location.latitude)}, ${Number(item.location.longitude)})`
          : `alert(${escAttr(name + ' is currently offline or location sharing is inactive.')})`;

        const isSos = Boolean(item.is_sos);

        let statusBadgeHtml = '';
        if (isSos) {
          statusBadgeHtml = `<span class="badge bg-danger text-white fw-bold px-2 py-0.5 d-inline-flex align-items-center gap-1 shadow-sm" style="font-size: 10.5px;"><i class="bi bi-exclamation-triangle-fill"></i>SOS ALERT</span>`;
        } else if (item.is_sharing) {
          statusBadgeHtml = `<span class="badge status-pill-live d-inline-flex align-items-center gap-1"><span class="status-pulse-dot"></span>Live</span>`;
        } else {
          statusBadgeHtml = `<span class="badge status-pill-offline d-inline-flex align-items-center gap-1"><i class="bi bi-cloud-slash"></i>Offline</span>`;
        }

        const distanceBadgeHtml = item.distance_km !== null
          ? `<span class="badge distance-pill d-inline-flex align-items-center gap-1"><i class="bi bi-geo-alt-fill text-primary"></i>${item.distance_km} km</span>`
          : '';

        return `
          <div class="member-card d-block ${isSos ? 'sos-active' : ''}" onclick="${clickHandler}">
            <!-- Top Row: Avatar + Name + Status Badges + Quick Locate Button -->
            <div class="d-flex align-items-center justify-content-between">
              <div class="d-flex align-items-center gap-2 gap-sm-3 min-w-0">
                <div class="member-avatar-box">
                  ${avatarContent}
                  ${batteryBadge}
                </div>
                <div class="min-w-0">
                  <div class="member-name-text text-truncate">${esc(name)}</div>
                  <div class="d-flex align-items-center gap-1.5 flex-wrap mt-1">
                    ${statusBadgeHtml}
                    ${distanceBadgeHtml}
                  </div>
                </div>
              </div>
              <div class="flex-shrink-0 ms-2">
                <button class="btn btn-sm btn-action-focus" title="Locate on Map" onclick="${clickHandler}">
                  <i class="bi bi-crosshair"></i>
                </button>
              </div>
            </div>

            <!-- Bottom Row: Username + Route & Remove Action Buttons -->
            <div class="d-flex align-items-center justify-content-between mt-2 pt-2 border-top border-secondary border-opacity-20" onclick="event.stopPropagation()">
              <span class="member-username-text text-truncate">@${esc(item.username)}</span>
              <div class="d-flex align-items-center gap-1.5">
                <button class="btn btn-sm btn-action-route" title="View Route History" onclick="app.viewLocationHistory(${Number(item.user_id)}, ${escAttr(name)})">
                  <i class="bi bi-clock-history me-1"></i>Route
                </button>
                <button class="btn btn-sm btn-action-remove" title="Remove Member" onclick="app.removeFriend(${Number(item.user_id)}, ${escAttr(name)})">
                  <i class="bi bi-person-x me-1"></i>Remove
                </button>
              </div>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {}
  }

  async loadGroups() {
    if (!this.token) return;
    try {
      const res = await this.authFetch('/api/groups/');
      if (!res.ok) return;
      const groups = await res.json();
      const list = document.getElementById('groupsList');
      if (!list) return;
      if (groups.length === 0) {
        list.innerHTML = `
          <div class="text-center text-muted small py-4">
            <i class="bi bi-diagram-3 fs-3 d-block mb-2 opacity-50"></i>
            <div>No family circles joined yet.</div>
            <div class="mt-1" style="font-size: 11.5px;">Click <strong>Create</strong> or <strong>Join</strong> above to get started!</div>
          </div>
        `;
        return;
      }
      list.innerHTML = groups.map(g => {
        const groupId = Number(g.id);
        const groupNameAttr = escAttr(g.name);
        const inviteCodeAttr = escAttr(g.invite_code);
        return `
        <div class="member-card d-block" style="cursor: pointer;" onclick="app.viewGroupMembers(${groupId}, ${groupNameAttr})">
          <div class="d-flex justify-content-between align-items-center mb-1">
            <span class="fw-bold text-main" style="font-size: 14.5px;"><i class="bi bi-diagram-3 me-1 text-primary"></i>${esc(g.name)}</span>
            <button class="btn btn-sm btn-outline-primary py-0.5 px-2 rounded-pill d-flex align-items-center gap-1" style="font-size: 11px;" onclick="event.stopPropagation(); app.viewGroupMembers(${groupId}, ${groupNameAttr})">
              <i class="bi bi-people-fill"></i><span>${Number(g.member_count) || 0} ${g.member_count === 1 ? 'member' : 'members'}</span><i class="bi bi-chevron-right ms-0.5" style="font-size: 9px;"></i>
            </button>
          </div>
          <div class="d-flex align-items-center justify-content-between mt-2 pt-1 border-top border-secondary border-opacity-20">
            <div class="small text-muted" style="font-size: 11.5px;">Code: <code class="text-primary fw-bold" style="font-size: 13px; letter-spacing: 0.5px;">${esc(g.invite_code)}</code></div>
            <div class="d-flex gap-1" onclick="event.stopPropagation()">
              <button class="btn btn-sm btn-outline-primary py-0 px-2 rounded-3" style="font-size: 11px;" onclick="event.stopPropagation(); app.viewGroupMembers(${groupId}, ${groupNameAttr})" title="View Circle Members">
                <i class="bi bi-people me-1"></i>Members
              </button>
              <button class="btn btn-sm btn-outline-secondary py-0 px-2 rounded-3" style="font-size: 11px;" onclick="event.stopPropagation(); app.copyInviteCode(${inviteCodeAttr}, this)" title="Copy Invite Code">
                <i class="bi bi-clipboard me-1"></i>Copy
              </button>
              ${g.role === 'admin'
                ? `<button class="btn btn-sm btn-outline-danger py-0 px-2 rounded-3" style="font-size: 11px;" onclick="event.stopPropagation(); app.deleteGroup(${groupId}, ${groupNameAttr})" title="Delete Circle">
                    <i class="bi bi-trash me-1"></i>Delete
                  </button>`
                : `<button class="btn btn-sm btn-outline-danger py-0 px-2 rounded-3" style="font-size: 11px;" onclick="event.stopPropagation(); app.leaveGroup(${groupId}, ${groupNameAttr})" title="Leave Circle">
                    <i class="bi bi-box-arrow-right me-1"></i>Leave
                  </button>`
              }
            </div>
          </div>
        </div>
      `;
      }).join('');
    } catch (e) {
      console.warn('Load groups error:', e);
    }
  }

  async viewGroupMembers(groupId, groupName) {
    if (!this.token) return;
    this.activeGroupId = groupId;
    this.activeGroupName = groupName;
    this.activeGroupInviteCode = '';

    const modalEl = document.getElementById('circleMembersModal');
    const titleEl = document.getElementById('circleMembersModalTitle');
    const subtitleEl = document.getElementById('circleMembersModalSubtitle');
    const codeEl = document.getElementById('circleMembersInviteCode');
    const badgeEl = document.getElementById('circleMembersCountBadge');
    const listEl = document.getElementById('circleMembersListContainer');

    if (titleEl) titleEl.innerHTML = `<i class="bi bi-diagram-3 me-2 text-primary"></i>${esc(groupName)}`;
    if (subtitleEl) subtitleEl.innerText = 'Loading circle members...';
    if (codeEl) codeEl.innerText = '--------';
    if (badgeEl) badgeEl.innerText = '...';
    if (listEl) {
      listEl.innerHTML = `
        <div class="text-center text-muted small py-4">
          <div class="spinner-border spinner-border-sm text-primary mb-2" role="status"></div>
          <div>Loading members...</div>
        </div>
      `;
    }

    if (modalEl) {
      const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
      modal.show();
    }

    try {
      const res = await this.authFetch(`/api/groups/${groupId}/members`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to load members' }));
        if (listEl) listEl.innerHTML = `<div class="text-danger small py-3">${esc(err.detail || 'Could not load members.')}</div>`;
        return;
      }

      const data = await res.json();
      this.activeGroupInviteCode = data.invite_code;
      if (codeEl) codeEl.innerText = data.invite_code;
      if (badgeEl) badgeEl.innerText = `${data.total_members} ${data.total_members === 1 ? 'member' : 'members'}`;
      if (subtitleEl) subtitleEl.innerText = `${data.total_members} ${data.total_members === 1 ? 'member' : 'members'} in this circle`;

      if (!data.members || data.members.length === 0) {
        if (listEl) listEl.innerHTML = `<div class="text-muted small text-center py-3">No members found in this circle.</div>`;
        return;
      }

      if (listEl) {
        listEl.innerHTML = data.members.map(m => {
          const memberName = String(m.full_name || 'Unknown');
          const avatarHtml = m.avatar_url
            ? `<img src="${safeUrl(m.avatar_url)}" alt="${esc(memberName)}" class="rounded-circle" style="width: 38px; height: 38px; object-fit: cover;">`
            : `<div class="rounded-circle bg-primary bg-opacity-15 text-primary d-flex align-items-center justify-content-center fw-bold" style="width: 38px; height: 38px; font-size: 15px;">${esc(memberName[0] ? memberName[0].toUpperCase() : '?')}</div>`;

          const roleBadge = m.role === 'admin'
            ? `<span class="badge bg-warning bg-opacity-20 text-warning border border-warning border-opacity-25 rounded-pill px-2 py-0.5" style="font-size: 10px;"><i class="bi bi-shield-fill-check me-1"></i>Admin</span>`
            : `<span class="badge bg-secondary bg-opacity-20 text-body-secondary rounded-pill px-2 py-0.5" style="font-size: 10px;">Member</span>`;

          const youBadge = m.is_me
            ? `<span class="badge bg-primary rounded-pill px-1.5 py-0.5 ms-1" style="font-size: 9.5px;">You</span>`
            : '';

          let liveBadge = '';
          if (m.is_sos) {
            liveBadge = `<span class="text-danger fw-bold small"><i class="bi bi-exclamation-triangle-fill me-1"></i>SOS</span>`;
          } else if (m.is_live) {
            liveBadge = `<span class="text-success fw-semibold small d-flex align-items-center gap-1"><span class="status-pulse-dot"></span>Live ${m.battery_level !== null ? `<span class="text-muted ms-1"><i class="bi bi-lightning-fill text-success"></i>${m.battery_level}%</span>` : ''}</span>`;
          } else {
            liveBadge = `<span class="text-muted small"><i class="bi bi-cloud-slash me-1"></i>Offline</span>`;
          }

          const canRemove = data.is_admin && !m.is_me;
          const canLocate = Boolean(m.latitude && m.longitude);

          return `
            <div class="p-2.5 rounded-3 border border-secondary border-opacity-20 bg-body-tertiary d-flex align-items-center justify-content-between gap-2">
              <div class="d-flex align-items-center gap-2.5 min-w-0">
                <div class="position-relative flex-shrink-0">
                  ${avatarHtml}
                  ${m.is_live ? `<span class="position-absolute bottom-0 end-0 p-1 bg-success border border-2 border-white rounded-circle"></span>` : ''}
                </div>
                <div class="overflow-hidden">
                  <div class="fw-bold text-truncate" style="font-size: 13.5px;">
                    ${esc(memberName)} ${youBadge}
                  </div>
                  <div class="d-flex align-items-center gap-1.5 flex-wrap mt-0.5">
                    ${roleBadge}
                    ${liveBadge}
                  </div>
                </div>
              </div>
              <div class="flex-shrink-0 d-flex align-items-center gap-1">
                ${canLocate ? `
                  <button class="btn btn-sm btn-outline-primary py-1 px-2 rounded-3 d-flex align-items-center gap-1" style="font-size: 11px;" onclick="app.locateMemberFromModal(${Number(m.latitude)}, ${Number(m.longitude)})">
                    <i class="bi bi-crosshair"></i><span class="d-none d-sm-inline">Locate</span>
                  </button>
                ` : ''}
                ${canRemove ? `
                  <button class="btn btn-sm btn-outline-danger py-1 px-2 rounded-3 d-flex align-items-center gap-1" style="font-size: 11px;" onclick="app.removeMemberFromGroup(${Number(groupId)}, ${Number(m.user_id)}, ${escAttr(memberName)})" title="Remove from Circle">
                    <i class="bi bi-person-x"></i><span class="d-none d-sm-inline">Remove</span>
                  </button>
                ` : ''}
              </div>
            </div>
          `;
        }).join('');
      }
    } catch (e) {
      if (listEl) listEl.innerHTML = `<div class="text-danger small py-3">Error loading circle members: ${esc(e.message)}</div>`;
    }
  }

  locateMemberFromModal(lat, lng) {
    const modalEl = document.getElementById('circleMembersModal');
    if (modalEl) {
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) modal.hide();
    }
    const sidebar = document.getElementById('mainSidebar');
    if (sidebar && window.innerWidth <= 768) {
      sidebar.classList.add('collapsed');
      document.body.classList.remove('sheet-expanded');
      document.body.classList.add('sheet-collapsed');
    }
    if (window.mapManager) {
      mapManager.focusLocation(lat, lng);
    }
  }

  async removeMemberFromGroup(groupId, targetUserId, targetName) {
    if (!confirm(`Are you sure you want to remove "${targetName}" from circle "${this.activeGroupName || 'this circle'}"?`)) return;
    try {
      const res = await this.authFetch(`/api/groups/${groupId}/members/${targetUserId}`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(data.message || `${targetName} removed from circle.`, 'info');
        this._lastFeedHash = null;
        if (window.mapManager && mapManager.markers && mapManager.markers[targetUserId]) {
          mapManager.markers[targetUserId].remove();
          delete mapManager.markers[targetUserId];
        }
        await this.viewGroupMembers(groupId, this.activeGroupName);
        await this.loadGroups();
        await this.loadFamilyFeed();
      } else {
        this.showToast(data.detail || 'Could not remove member from circle.', 'danger');
      }
    } catch (e) {
      this.showToast('Network error: ' + e.message, 'danger');
    }
  }

  copyCurrentCircleInviteCode(btn) {
    if (!this.activeGroupInviteCode) return;
    this.copyInviteCode(this.activeGroupInviteCode, btn);
  }

  async leaveGroup(groupId, groupName) {
    if (!confirm(`Are you sure you want to leave circle "${groupName}"?`)) return;
    try {
      const res = await this.authFetch(`/api/groups/${groupId}/leave`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(`You left circle "${groupName}".`, 'info');
        this._lastFeedHash = null;
        await this.loadGroups();
        await this.loadFamilyFeed();
      } else {
        this.showToast(data.detail || 'Could not leave circle', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    }
  }

  async deleteGroup(groupId, groupName) {
    if (!confirm(`Are you sure you want to completely DELETE circle "${groupName}"? All circle members will be removed.`)) return;
    try {
      const res = await this.authFetch(`/api/groups/${groupId}/delete`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(data.message || `Circle "${groupName}" deleted.`, 'info');
        this._lastFeedHash = null;
        await this.loadGroups();
        await this.loadFamilyFeed();
      } else {
        this.showToast(data.detail || 'Could not delete circle', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    }
  }

  async removeFriend(friendUserId, friendName) {
    if (!confirm(`Are you sure you want to remove ${friendName} from your family list?`)) return;
    try {
      const res = await this.authFetch(`/api/friends/${friendUserId}`, { method: 'DELETE' });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(data.message || `${friendName} removed from family list.`, 'info');
        this._lastFeedHash = null;
        if (window.mapManager && mapManager.markers && mapManager.markers[friendUserId]) {
          mapManager.markers[friendUserId].remove();
          delete mapManager.markers[friendUserId];
        }
        await this.loadFamilyFeed();
        await this.loadGroups();
      } else {
        this.showToast(data.detail || 'Could not remove member.', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    }
  }

  copyInviteCode(code, btn) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(code).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = `<i class="bi bi-check2 text-success me-1"></i>Copied!`;
        this.showToast(`Invite code ${code} copied! Share it with family.`, 'success');
        setTimeout(() => { btn.innerHTML = orig; }, 1800);
      }).catch(() => {
        prompt('Copy circle invite code:', code);
      });
    } else {
      prompt('Copy circle invite code:', code);
    }
  }

  async viewLocationHistory(userId, userName, hours = 24) {
    if (!this.token) return;
    this.currentHistoryUserId = userId;
    this.currentHistoryUserName = userName;
    this.currentHistoryHours = hours;

    try {
      const res = await this.authFetch(`/api/locations/history/${userId}?hours=${hours}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to fetch history' }));
        alert('Route History: ' + (err.detail || 'Could not fetch history'));
        return;
      }

      const points = await res.json();
      if (!points || points.length === 0) {
        alert(`No location history found for ${userName} in the past ${hours} hours.`);
        return;
      }

      mapManager.drawRouteHistory(points, userName);

      // Show banner
      const banner = document.getElementById('routeHistoryBanner');
      const title = document.getElementById('routeBannerTitle');
      const sub = document.getElementById('routeBannerSubtitle');
      if (banner) {
        if (title) title.innerText = `Route: ${userName}`;
        if (sub) sub.innerText = `Past ${hours}h • ${points.length} points recorded`;
        banner.classList.remove('d-none');
      }

      // If mobile, collapse sidebar to give full view of route on map
      const sidebar = document.getElementById('mainSidebar');
      const chevron = document.getElementById('sheetChevronIcon');
      if (sidebar && window.innerWidth <= 768) {
        sidebar.classList.add('collapsed');
        document.body.classList.remove('sheet-expanded');
        document.body.classList.add('sheet-collapsed');
        if (chevron) chevron.className = 'bi bi-chevron-up text-muted ms-1 fs-6';
      }
    } catch (e) {
      alert('Error fetching route history: ' + e.message);
    }
  }

  reloadRouteHistory(hours) {
    if (this.currentHistoryUserId) {
      this.viewLocationHistory(this.currentHistoryUserId, this.currentHistoryUserName, hours);
    }
  }

  clearRouteHistory() {
    mapManager.clearRouteHistory();
    const banner = document.getElementById('routeHistoryBanner');
    if (banner) banner.classList.add('d-none');
    this.currentHistoryUserId = null;
    this.currentHistoryUserName = null;
  }

  async loadRequests() {
    if (!this.token) return;
    try {
      const res = await this.authFetch('/api/friends/requests');
      if (!res.ok) return;
      const reqs = await res.json();

      const badge = document.getElementById('pendingRequestsCountBadge');
      if (badge) {
        if (reqs.length > 0) {
          badge.innerText = reqs.length;
          badge.classList.remove('d-none');
        } else {
          badge.classList.add('d-none');
        }
      }

      const list = document.getElementById('requestsList');
      if (!list) return;

      const reqsHash = JSON.stringify(reqs);
      if (this._lastReqsHash === reqsHash) return;
      this._lastReqsHash = reqsHash;

      if (reqs.length === 0) {
        list.innerHTML = `<div class="text-center text-muted small py-3">No pending requests.</div>`;
        return;
      }
      list.innerHTML = reqs.map(r => `
        <div class="member-card">
          <div class="min-w-0">
            <div class="fw-bold" style="font-size: 14px;">${esc(r.sender.full_name)}</div>
            <div class="text-muted" style="font-size: 11.5px;">@${esc(r.sender.username)}</div>
          </div>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-success py-1 px-3 rounded-start-3" title="Accept" onclick="app.respondRequest(${r.id}, 'accept')"><i class="bi bi-check-lg"></i></button>
            <button class="btn btn-danger py-1 px-3 rounded-end-3" title="Decline" onclick="app.respondRequest(${r.id}, 'reject')"><i class="bi bi-x-lg"></i></button>
          </div>
        </div>
      `).join('');
    } catch (e) {}
  }

  toggleMobileSidebar() {
    const sidebar = document.getElementById('mainSidebar');
    const chevron = document.getElementById('sheetChevronIcon');
    if (sidebar) {
      const willExpand = sidebar.classList.contains('collapsed');
      if (willExpand) {
        sidebar.classList.remove('collapsed');
        document.body.classList.add('sheet-expanded');
        document.body.classList.remove('sheet-collapsed');
        if (chevron) chevron.className = 'bi bi-chevron-down text-muted ms-1 fs-6';
      } else {
        sidebar.classList.add('collapsed');
        document.body.classList.remove('sheet-expanded');
        document.body.classList.add('sheet-collapsed');
        if (chevron) chevron.className = 'bi bi-chevron-up text-muted ms-1 fs-6';
      }
      setTimeout(() => {
        if (window.mapManager && mapManager.map && mapManager.map.invalidateSize) {
          mapManager.map.invalidateSize();
        }
      }, 350);
    }
  }

  initMobileGestures() {
    const zone = document.getElementById('sidebarDragZone') || document.getElementById('sidebarDragHandle');
    if (!zone) return;
    let startY = 0;

    zone.addEventListener('touchstart', (e) => {
      startY = e.touches[0].clientY;
    }, { passive: true });

    zone.addEventListener('touchend', (e) => {
      const endY = e.changedTouches[0].clientY;
      const diff = endY - startY;
      const sidebar = document.getElementById('mainSidebar');
      const chevron = document.getElementById('sheetChevronIcon');
      if (!sidebar) return;

      if (diff > 30) {
        // Swiped down -> collapse bottom sheet
        sidebar.classList.add('collapsed');
        document.body.classList.remove('sheet-expanded');
        document.body.classList.add('sheet-collapsed');
        if (chevron) chevron.className = 'bi bi-chevron-up text-muted ms-1 fs-6';
      } else if (diff < -30) {
        // Swiped up -> expand bottom sheet
        sidebar.classList.remove('collapsed');
        document.body.classList.add('sheet-expanded');
        document.body.classList.remove('sheet-collapsed');
        if (chevron) chevron.className = 'bi bi-chevron-down text-muted ms-1 fs-6';
      }

      setTimeout(() => {
        if (window.mapManager && mapManager.map && mapManager.map.invalidateSize) {
          mapManager.map.invalidateSize();
        }
      }, 350);
    }, { passive: true });
  }

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-bs-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    this.applyTheme(next);
  }

  applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    localStorage.setItem('theme', theme);
    const btn = document.getElementById('themeToggleBtn');
    if (btn) btn.innerHTML = theme === 'dark' ? '<i class="bi bi-moon-stars"></i>' : '<i class="bi bi-sun"></i>';
  }

  showToast(msg, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) {
      alert(msg);
      return;
    }
    const toast = document.createElement('div');
    toast.className = `app-toast toast-${type}`;
    const iconClass = type === 'success'
      ? 'bi-check-circle-fill text-success'
      : (type === 'danger' ? 'bi-exclamation-triangle-fill text-danger' : 'bi-info-circle-fill text-primary');
    toast.innerHTML = `<i class="bi ${iconClass} fs-5"></i><span>${esc(msg)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(15px)';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  openAddFriendModal() {
    const el = document.getElementById('addFriendModal');
    if (el) {
      const input = document.getElementById('targetFriendIdentifier');
      if (input) input.value = '';
      bootstrap.Modal.getOrCreateInstance(el).show();
    }
  }

  openCreateGroupModal() {
    const el = document.getElementById('createGroupModal');
    if (el) {
      const input = document.getElementById('groupNameInput');
      if (input) input.value = '';
      bootstrap.Modal.getOrCreateInstance(el).show();
    }
  }

  openJoinGroupModal() {
    const el = document.getElementById('joinGroupModal');
    if (el) {
      const input = document.getElementById('joinGroupCodeInput');
      if (input) input.value = '';
      bootstrap.Modal.getOrCreateInstance(el).show();
    }
  }

  async handleSendFriendRequest(event) {
    if (event) event.preventDefault();
    const input = document.getElementById('targetFriendIdentifier');
    const val = input ? input.value.trim() : '';
    if (!val) {
      this.showToast('Please enter a username or email.', 'danger');
      return;
    }

    const btn = document.getElementById('btnSendFriendRequest') || (event && event.submitter);
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Sending...';
    }

    try {
      const res = await this.authFetch('/api/friends/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username_or_email: val })
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(data.message || 'Friend request sent successfully!', 'success');
        if (input) input.value = '';
        const modalEl = document.getElementById('addFriendModal');
        if (modalEl) {
          const inst = bootstrap.Modal.getInstance(modalEl);
          if (inst) inst.hide();
        }
        await this.loadFamilyFeed();
        await this.loadRequests();
      } else {
        this.showToast(data.detail || 'Could not send friend request.', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    }
  }

  async handleCreateGroup(event) {
    if (event) event.preventDefault();
    const input = document.getElementById('groupNameInput');
    const name = input ? input.value.trim() : '';
    if (!name) {
      this.showToast('Please enter a circle name.', 'danger');
      return;
    }

    const btn = document.getElementById('btnCreateGroup') || (event && event.submitter);
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';
    }

    try {
      const res = await this.authFetch('/api/groups/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(`Circle "${data.name}" created! Invite code: ${data.invite_code}`, 'success');
        if (input) input.value = '';
        const modalEl = document.getElementById('createGroupModal');
        if (modalEl) {
          const inst = bootstrap.Modal.getInstance(modalEl);
          if (inst) inst.hide();
        }
        await this.loadGroups();
        await this.loadFamilyFeed();
      } else {
        this.showToast(data.detail || 'Failed to create circle.', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    }
  }

  async handleJoinGroup(event) {
    if (event) event.preventDefault();
    const input = document.getElementById('joinGroupCodeInput');
    const code = input ? input.value.trim().toUpperCase() : '';
    if (!code) {
      this.showToast('Please enter an invite code.', 'danger');
      return;
    }

    const btn = document.getElementById('btnJoinGroup') || (event && event.submitter);
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Joining...';
    }

    try {
      const res = await this.authFetch('/api/groups/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: code })
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(data.message || 'Joined circle successfully!', 'success');
        if (input) input.value = '';
        const modalEl = document.getElementById('joinGroupModal');
        if (modalEl) {
          const inst = bootstrap.Modal.getInstance(modalEl);
          if (inst) inst.hide();
        }
        await this.loadGroups();
        await this.loadFamilyFeed();
      } else {
        this.showToast(data.detail || 'Failed to join circle.', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    }
  }

  async respondRequest(reqId, action) {
    try {
      const res = await this.authFetch(`/api/friends/requests/${reqId}/respond?action=${action}`, {
        method: 'POST'
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        this.showToast(data.message || `Request ${action}ed!`, 'success');
        await this.loadRequests();
        await this.loadFamilyFeed();
      } else {
        this.showToast(data.detail || 'Action failed.', 'danger');
      }
    } catch (err) {
      this.showToast('Network error: ' + err.message, 'danger');
    }
  }
}

const app = new App();
window.app = app;
window.showToast = (msg, type) => app.showToast(msg, type);
window.mapManager = mapManager;
window.locationTracker = locationTracker;

window.addEventListener('DOMContentLoaded', () => app.init());