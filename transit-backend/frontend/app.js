'use strict';

// ── Constants ─────────────────────────────────────────────────────────────
const HISTORY_KEY    = 'drt_chat_history';
const ROUTE_KEY      = 'drt_saved_route';
const THEME_KEY      = 'drt_theme';
const AUTH_TOKEN_KEY = 'drt_auth_token';
const AUTH_USER_KEY  = 'drt_auth_user';
const TERMS_KEY      = 'drt_terms_accepted'; // set to '1' once user agrees

// Password complexity: min 8, max 32, uppercase, number, special char
const PASSWORD_REGEX = /^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+\[\]{};:'",.<>/?\\|~`]).{8,32}$/;

// ── Auth state ────────────────────────────────────────────────────────────
let _authToken = null;  // JWT string, set after login
let _authUser  = null;  // { id, email, display_name }

// ── Auth helpers ──────────────────────────────────────────────────────────

function authHeaders() {
  return _authToken ? { 'Authorization': `Bearer ${_authToken}` } : {};
}

function saveAuthSession(token, user) {
  _authToken = token;
  _authUser  = user;
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  } catch (_) {}
}

function clearAuthSession() {
  _authToken = null;
  _authUser  = null;
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
    localStorage.removeItem(HISTORY_KEY);
    localStorage.removeItem(ROUTE_KEY);
  } catch (_) {}
}

function loadAuthSession() {
  try {
    _authToken = localStorage.getItem(AUTH_TOKEN_KEY) || null;
    const raw  = localStorage.getItem(AUTH_USER_KEY);
    _authUser  = raw ? JSON.parse(raw) : null;
  } catch (_) {
    _authToken = null;
    _authUser  = null;
  }
}

// ── Auth overlay DOM refs ──────────────────────────────────────────────────
const authOverlay    = document.getElementById('auth-overlay');
const authError      = document.getElementById('auth-error');

// Views
const viewLogin      = document.getElementById('auth-view-login');
const viewSignup     = document.getElementById('auth-view-signup');
const viewForgot     = document.getElementById('auth-view-forgot');
const viewReset      = document.getElementById('auth-view-reset');
const viewTerms      = document.getElementById('auth-view-terms');

// Forms
const formLogin      = document.getElementById('form-login');
const formSignup     = document.getElementById('form-signup');
const formForgot     = document.getElementById('form-forgot');
const formReset      = document.getElementById('form-reset');

// View-switch buttons
const btnShowSignup  = document.getElementById('btn-show-signup');
const btnShowLogin   = document.getElementById('btn-show-login');
const btnShowForgot  = document.getElementById('btn-show-forgot');
const btnBackLogin   = document.getElementById('btn-back-to-login');

// Terms buttons
const btnAcceptTerms = document.getElementById('btn-accept-terms');
const btnDeclineTerms = document.getElementById('btn-decline-terms');
const btnShowTermsFromLogin  = document.getElementById('btn-show-terms-from-login');
const btnShowTermsFromSignup = document.getElementById('btn-show-terms-from-signup');
const btnShowTermsFromSignupBottom = document.getElementById('btn-show-terms-from-signup-bottom');

// Location error banner
const locationErrorBanner = document.getElementById('location-error-banner');
const btnRetryLocation    = document.getElementById('btn-retry-location');

// AI status notice
const aiStatusNotice = document.getElementById('ai-status-notice');
const btnCheckAI     = document.getElementById('btn-check-ai');

// Social buttons
const btnGoogleLogin   = document.getElementById('btn-google-login');

// Sidebar user info
const sidebarUser      = document.getElementById('sidebar-user');
const sidebarUserAvatar= document.getElementById('sidebar-user-avatar');
const sidebarUserName  = document.getElementById('sidebar-user-name');
const sidebarUserEmail = document.getElementById('sidebar-user-email');
const btnLogout        = document.getElementById('btn-logout');

// ── Auth overlay helpers ──────────────────────────────────────────────────

function showAuthView(viewEl) {
  [viewLogin, viewSignup, viewForgot, viewReset, viewTerms].forEach(v => v.classList.add('hidden'));
  viewEl.classList.remove('hidden');
  clearAuthError();
  // Focus the first input in the view for accessibility
  const firstInput = viewEl.querySelector('input, button');
  if (firstInput) setTimeout(() => firstInput.focus(), 50);
}

// ── Terms helpers ────────────────────────────────────────────────────

function hasAcceptedTerms() {
  try { return localStorage.getItem(TERMS_KEY) === '1'; } catch (_) { return false; }
}

function markTermsAccepted() {
  try { localStorage.setItem(TERMS_KEY, '1'); } catch (_) {}
}

// Source view to return to after viewing terms ('login' or 'signup')
let _termsReturnView = 'login';

function showTermsView(returnView) {
  _termsReturnView = returnView || 'login';
  showAuthView(viewTerms);
  // Scroll terms content to top
  const content = document.querySelector('.terms-content');
  if (content) content.scrollTop = 0;
}

function showAuthOverlay() {
  authOverlay.classList.remove('hidden');
  authOverlay.removeAttribute('aria-hidden');
  showAuthView(viewLogin);
}

function hideAuthOverlay() {
  authOverlay.classList.add('hidden');
  authOverlay.setAttribute('aria-hidden', 'true');
}

function showAuthError(msg) {
  authError.textContent = msg;
  authError.classList.remove('hidden');
}

function clearAuthError() {
  authError.textContent = '';
  authError.classList.add('hidden');
}

function setAuthBtnLoading(btn, loading) {
  btn.disabled = loading;
  btn.setAttribute('aria-busy', String(loading));
  if (loading) {
    btn.dataset.origText = btn.textContent;
    btn.textContent = 'Please wait…';
  } else if (btn.dataset.origText) {
    btn.textContent = btn.dataset.origText;
  }
}

// ── Sidebar user display ──────────────────────────────────────────────────

function updateSidebarUser(user) {
  if (!user) {
    sidebarUser.classList.add('hidden');
    if (btnLogout) btnLogout.classList.add('hidden');
    return;
  }
  const initials = (user.display_name || user.email || '?')
    .split(' ')
    .map(w => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  sidebarUserAvatar.textContent = initials;
  sidebarUserName.textContent   = user.display_name || '';
  sidebarUserEmail.textContent  = user.email || '';
  sidebarUser.classList.remove('hidden');
  if (btnLogout) btnLogout.classList.remove('hidden');
}

// ── Display name editing ──────────────────────────────────────────────────

const btnEditDisplayName   = document.getElementById('btn-edit-display-name');
const displayNameEditForm  = document.getElementById('display-name-edit-form');
const displayNameInput     = document.getElementById('display-name-input');
const btnSaveDisplayName   = document.getElementById('btn-save-display-name');
const btnCancelDisplayName = document.getElementById('btn-cancel-display-name');
const displayNameError     = document.getElementById('display-name-error');

// Validation: letters, digits, spaces, underscores, hyphens — max 32 chars
const DISPLAY_NAME_RE  = /^[\w\s\-]+$/u;
const DISPLAY_NAME_MAX = 32;

function validateDisplayName(value) {
  const v = value.trim();
  if (!v)                        return 'Display name must not be blank.';
  if (v.length > DISPLAY_NAME_MAX) return `Display name must not exceed ${DISPLAY_NAME_MAX} characters.`;
  if (!DISPLAY_NAME_RE.test(v))  return 'Only letters, numbers, spaces, underscores, or hyphens are allowed.';
  return null;
}

function showDisplayNameError(msg) {
  displayNameError.textContent = msg;
  displayNameError.classList.remove('hidden');
}

function hideDisplayNameError() {
  displayNameError.textContent = '';
  displayNameError.classList.add('hidden');
}

function openDisplayNameForm() {
  displayNameInput.value = _authUser ? (_authUser.display_name || '') : '';
  hideDisplayNameError();
  displayNameEditForm.classList.remove('hidden');
  displayNameInput.focus();
  displayNameInput.select();
}

function closeDisplayNameForm() {
  displayNameEditForm.classList.add('hidden');
  hideDisplayNameError();
}

if (btnEditDisplayName) {
  btnEditDisplayName.addEventListener('click', () => {
    const isOpen = !displayNameEditForm.classList.contains('hidden');
    isOpen ? closeDisplayNameForm() : openDisplayNameForm();
  });
}

if (btnCancelDisplayName) {
  btnCancelDisplayName.addEventListener('click', closeDisplayNameForm);
}

if (btnSaveDisplayName) {
  btnSaveDisplayName.addEventListener('click', saveDisplayName);
}

if (displayNameInput) {
  displayNameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter')  { e.preventDefault(); saveDisplayName(); }
    if (e.key === 'Escape') { closeDisplayNameForm(); }
  });
  // Live validation feedback while typing
  displayNameInput.addEventListener('input', () => {
    const err = validateDisplayName(displayNameInput.value);
    err ? showDisplayNameError(err) : hideDisplayNameError();
  });
}

async function saveDisplayName() {
  const newName = displayNameInput.value.trim();
  const err = validateDisplayName(newName);
  if (err) { showDisplayNameError(err); displayNameInput.focus(); return; }

  btnSaveDisplayName.disabled = true;
  btnSaveDisplayName.textContent = '…';
  hideDisplayNameError();

  try {
    const res = await fetch('/auth/display-name', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ display_name: newName }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      // Pydantic validation errors arrive as {detail: [{msg: ...}]} or {detail: "..."}
      const msg = Array.isArray(data.detail)
        ? data.detail.map(e => e.msg).join(' ')
        : (data.detail || 'Could not save display name.');
      showDisplayNameError(msg);
    } else {
      // Update local auth state and sidebar
      if (_authUser) {
        _authUser.display_name = data.display_name;
        try { localStorage.setItem(AUTH_USER_KEY, JSON.stringify(_authUser)); } catch (_) {}
      }
      updateSidebarUser(_authUser);
      closeDisplayNameForm();
    }
  } catch (_) {
    showDisplayNameError('Could not reach the server. Please try again.');
  } finally {
    btnSaveDisplayName.disabled = false;
    btnSaveDisplayName.textContent = 'Save';
  }
}

// ── Auth API calls ────────────────────────────────────────────────────────

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

async function verifyToken(token) {
  /** Calls /auth/me with the given token. Returns user dict or null. */
  try {
    const res = await fetch('/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (res.ok) return await res.json();
  } catch (_) {}
  return null;
}

// ── Login form ────────────────────────────────────────────────────────────

formLogin.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAuthError();
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  if (!email)    { showAuthError('Email is required.'); return; }
  if (email.length > 254) { showAuthError('Email must not exceed 254 characters.'); return; }
  if (!password) { showAuthError('Password is required.'); return; }

  const btn = document.getElementById('btn-login');
  if (btn.disabled) return; // idempotency guard
  setAuthBtnLoading(btn, true);
  try {
    const data = await apiPost('/auth/login', { email, password });
    saveAuthSession(data.token, data.user);
    onAuthSuccess(data.user);
  } catch (err) {
    showAuthError(err.message);
  } finally {
    setAuthBtnLoading(btn, false);
  }
});

// ── Signup form ───────────────────────────────────────────────────────────

formSignup.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAuthError();
  const name     = document.getElementById('signup-name').value.trim();
  const email    = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;

  if (!name)    { showAuthError('Display name is required.'); return; }
  if (!email)   { showAuthError('Email is required.'); return; }
  if (email.length > 254) { showAuthError('Email must not exceed 254 characters.'); return; }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showAuthError('Please enter a valid email address.'); return; }
  if (!password) { showAuthError('Password is required.'); return; }
  if (password.length < 8)  { showAuthError('Password must be at least 8 characters.'); return; }
  if (password.length > 32) { showAuthError('Password must not exceed 32 characters.'); return; }
  if (!/[A-Z]/.test(password)) { showAuthError('Password must contain at least one uppercase letter.'); return; }
  if (!/\d/.test(password))    { showAuthError('Password must contain at least one number.'); return; }
  if (!/[!@#$%^&*()\-_=+\[\]{};:'",.<>/?\\|~`]/.test(password)) {
    showAuthError('Password must contain at least one special character (e.g. !@#$%^&*).');
    return;
  }
  const termsChecked = document.getElementById('signup-terms').checked;
  if (!termsChecked) {
    showAuthError('You must agree to the Terms of Use & Privacy Notice to create an account.');
    return;
  }

  const btn = document.getElementById('btn-signup');
  if (btn.disabled) return; // idempotency guard
  setAuthBtnLoading(btn, true);
  try {
    const data = await apiPost('/auth/signup', { email, password, display_name: name });
    markTermsAccepted();
    saveAuthSession(data.token, data.user);
    onAuthSuccess(data.user);
  } catch (err) {
    showAuthError(err.message);
  } finally {
    setAuthBtnLoading(btn, false);
  }
});

// ── Forgot password form ──────────────────────────────────────────────────

formForgot.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAuthError();
  const email = document.getElementById('forgot-email').value.trim();
  if (!email) { showAuthError('Please enter your email address.'); return; }

  const btn = document.getElementById('btn-forgot');
  setAuthBtnLoading(btn, true);
  try {
    const data = await apiPost('/auth/forgot-password', { email });
    // Show success inline (don't hide overlay)
    authError.textContent = data.message;
    authError.classList.remove('hidden');
    authError.classList.add('auth-error--success');
    formForgot.reset();
  } catch (err) {
    showAuthError(err.message);
  } finally {
    setAuthBtnLoading(btn, false);
  }
});

// ── Reset password form ───────────────────────────────────────────────────

formReset.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAuthError();
  const newPassword = document.getElementById('reset-password').value;
  const resetToken  = new URLSearchParams(window.location.search).get('reset_token');

  if (!newPassword || newPassword.length < 8) {
    showAuthError('Password must be at least 8 characters.');
    return;
  }
  if (!resetToken) {
    showAuthError('Reset token missing. Please use the link from your email.');
    return;
  }

  const btn = document.getElementById('btn-reset');
  setAuthBtnLoading(btn, true);
  try {
    await apiPost('/auth/reset-password', { token: resetToken, new_password: newPassword });
    // Clear the token from the URL silently
    window.history.replaceState({}, '', '/');
    authError.textContent = 'Password updated! You can now sign in.';
    authError.classList.remove('hidden');
    authError.classList.add('auth-error--success');
    setTimeout(() => showAuthView(viewLogin), 2000);
  } catch (err) {
    showAuthError(err.message);
  } finally {
    setAuthBtnLoading(btn, false);
  }
});

// ── OAuth popup flow ──────────────────────────────────────────────────────

function openOAuthPopup(path) {
  const w = 520, h = 640;
  const left = Math.round(window.screenX + (window.outerWidth  - w) / 2);
  const top  = Math.round(window.screenY + (window.outerHeight - h) / 2);
  window.open(path, 'drt_oauth', `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`);
}

window.addEventListener('message', (event) => {
  // Only accept messages from the same origin
  if (event.origin !== window.location.origin) return;

  const { type, token, message } = event.data || {};

  if (type === 'oauth_success' && token) {
    // Verify and apply the token
    verifyToken(token).then((user) => {
      if (user) {
        saveAuthSession(token, user);
        onAuthSuccess(user);
      } else {
        showAuthError('OAuth sign-in failed. Please try again.');
      }
    });
  } else if (type === 'oauth_error') {
    showAuthError(message || 'OAuth sign-in failed. Please try again.');
  }
});

if (btnGoogleLogin) {
  btnGoogleLogin.addEventListener('click', () => openOAuthPopup('/auth/google/login'));
}

// ── Password show / hide toggles ──────────────────────────────────────────
// Single delegated listener handles all .pw-toggle buttons in the auth overlay
authOverlay.addEventListener('click', (e) => {
  const btn = e.target.closest('.pw-toggle');
  if (!btn) return;
  const input   = btn.closest('.pw-wrap').querySelector('input');
  const iconShow = btn.querySelector('.pw-icon--show');
  const iconHide = btn.querySelector('.pw-icon--hide');
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  btn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
  iconShow.style.display = isHidden ? 'none'  : '';
  iconHide.style.display = isHidden ? ''      : 'none';
  input.focus();
});



if (btnShowSignup)  btnShowSignup.addEventListener('click',  () => showAuthView(viewSignup));
if (btnShowLogin)   btnShowLogin.addEventListener('click',   () => showAuthView(viewLogin));
if (btnShowForgot)  btnShowForgot.addEventListener('click',  () => showAuthView(viewForgot));
if (btnBackLogin)   btnBackLogin.addEventListener('click',   () => {
  authError.classList.remove('auth-error--success');
  showAuthView(viewLogin);
});

// Terms view navigation
if (btnShowTermsFromLogin)       btnShowTermsFromLogin.addEventListener('click',       () => showTermsView('login'));
if (btnShowTermsFromSignup)      btnShowTermsFromSignup.addEventListener('click',      () => showTermsView('signup'));
if (btnShowTermsFromSignupBottom) btnShowTermsFromSignupBottom.addEventListener('click', () => showTermsView('signup'));

if (btnAcceptTerms) {
  btnAcceptTerms.addEventListener('click', () => {
    markTermsAccepted();
    if (_termsReturnView === 'signup') {
      // Tick the checkbox automatically since they accepted in T&C view
      const termsChk = document.getElementById('signup-terms');
      if (termsChk) termsChk.checked = true;
      showAuthView(viewSignup);
    } else {
      showAuthView(viewLogin);
    }
  });
}

if (btnDeclineTerms) {
  btnDeclineTerms.addEventListener('click', () => {
    // Clear any session and stay on login
    clearAuthSession();
    showAuthView(viewLogin);
  });
}

// ── Logout ────────────────────────────────────────────────────────────────

if (btnLogout) {
  btnLogout.addEventListener('click', () => {
    clearAuthSession();
    apiHistory = [];
    gpsCoords  = null;
    gpsRequested = false;
    _currentSessionId = null;
    if (activeFetch) { activeFetch.abort(); activeFetch = null; }
    chatArea.innerHTML = '';
    updateSidebarUser(null);
    if (chatHistorySection) chatHistorySection.classList.add('hidden');
    if (chatHistoryList)    chatHistoryList.innerHTML = '';
    showWelcome();
    showAuthOverlay();
  });
}

// ── Post-auth success ─────────────────────────────────────────────────────

function onAuthSuccess(user) {
  // If user hasn't accepted T&C yet, show the T&C view instead of the app
  if (!hasAcceptedTerms()) {
    _termsReturnView = 'login';
    showTermsView('login');
    // Wait for acceptance; btnAcceptTerms handler will call onAuthSuccess-like logic
    // via the markTermsAccepted + showAuthView flow, so we need to re-trigger after acceptance.
    // Override the accept button for this one-time post-auth flow:
    const acceptOnce = () => {
      markTermsAccepted();
      btnAcceptTerms.removeEventListener('click', acceptOnce);
      _finalizeAuthSuccess(user);
    };
    btnAcceptTerms.addEventListener('click', acceptOnce);
    return;
  }
  _finalizeAuthSuccess(user);
}

async function _finalizeAuthSuccess(user) {
  hideAuthOverlay();
  updateSidebarUser(user);
  loadHistory();
  renderHistory();
  if (apiHistory.length === 0) showWelcome();
  checkSavedRoute();
  fetchAndRenderHistory();
  fetchSubscriptionStatus();  // load tier + quota on every login

  // Request GPS on login — triggers the browser permission prompt if not yet
  // granted, and resolves immediately if already allowed.
  enforceLocation();
  // Check AI availability in background (non-blocking)
  checkAIStatus();
}

// ── AI availability ───────────────────────────────────────────────────────

/**
 * Call /ai-status (no LLM invoked — just checks env keys).
 * Updates the AI notice strip and textarea placeholder.
 */
async function checkAIStatus() {
  try {
    const res = await fetch('/ai-status', { headers: authHeaders() });
    if (res.ok) {
      const data = await res.json();
      _aiAvailable = data.available === true;
    } else {
      _aiAvailable = false;
    }
  } catch (_) {
    _aiAvailable = false;
  }
  _applyAIStatusUI();
}

function _applyAIStatusUI() {
  const inputBox = document.querySelector('.input-bar__box');
  if (_aiAvailable === false) {
    if (aiStatusNotice) aiStatusNotice.classList.remove('hidden');
    // Hide the entire chat input box — chips are the only interaction available
    if (inputBox) inputBox.classList.add('hidden');
  } else {
    if (aiStatusNotice) aiStatusNotice.classList.add('hidden');
    if (inputBox) inputBox.classList.remove('hidden');
    if (messageInput && !_locationBlocked) {
      messageInput.setAttribute('placeholder', 'Ask about buses, delays, routes\u2026');
    }
  }
  // Refresh the welcome screen chips now that AI status is known
  const welcomeEl = document.getElementById('welcome-screen');
  if (welcomeEl) _refreshWelcomeChips(welcomeEl);
}

if (btnCheckAI) {
  btnCheckAI.addEventListener('click', async () => {
    btnCheckAI.disabled = true;
    btnCheckAI.textContent = 'Checking…';
    await checkAIStatus();
    btnCheckAI.disabled = false;
    btnCheckAI.textContent = 'Check again';
  });
}

// ── Location enforcement ──────────────────────────────────────────────────

function showLocationError() {
  _locationBlocked = true;
  if (locationErrorBanner) locationErrorBanner.classList.remove('hidden');
  // Show manual location fallback so the user can still type their area
  showLocationFallback();
  // Input stays enabled — user can type while entering location manually
}

function hideLocationError() {
  _locationBlocked = false;
  if (locationErrorBanner) locationErrorBanner.classList.add('hidden');
  // Hide manual fallback only if GPS is now working
  if (gpsCoords && locationFallback) locationFallback.classList.add('hidden');
  setSendDisabled(false);
  messageInput.setAttribute('placeholder', 'Ask about buses, delays, routes\u2026');
}

async function enforceLocation() {
  if (gpsCoords) { hideLocationError(); return; }

  if (!navigator.geolocation) {
    showLocationFallback(); // no GPS support at all — just offer the text fallback
    return;
  }

  // Use the Permissions API to check current state without triggering a browser
  // prompt. This prevents the banner from flashing on every page load when the
  // user has already chosen "Allow for every visit".
  if (navigator.permissions) {
    try {
      const permStatus = await navigator.permissions.query({ name: 'geolocation' });

      // React to future changes (e.g. user revokes or grants in browser settings)
      permStatus.onchange = () => enforceLocation();

      if (permStatus.state === 'denied') {
        // Browser has blocked location — no point calling getCurrentPosition
        showLocationError();
        return;
      }
      // 'granted' or 'prompt' — fall through to getCurrentPosition below
    } catch (_) {
      // Permissions API unavailable (e.g. Firefox private browsing) — fall through
    }
  }

  const coords = await getLocation();
  if (coords) {
    gpsCoords = coords;
    gpsRequested = true;
    hideLocationError();
    messageInput.focus();
    // GPS just resolved — refresh welcome chips so location-based ones appear
    const welcomeEl = document.getElementById('welcome-screen');
    if (welcomeEl) _fetchAndReplaceChips(welcomeEl);
  } else {
    // getLocation() returned null for one of two reasons:
    //   1. Permission was actually denied → show the notice strip
    //   2. GPS technically failed (no hardware, signal lost, timeout) even though
    //      the user already allowed location → just show the text fallback quietly
    let permDenied = !navigator.permissions; // assume denied only if we can't check
    if (navigator.permissions) {
      try {
        const st = await navigator.permissions.query({ name: 'geolocation' });
        permDenied = st.state === 'denied';
      } catch (_) {
        permDenied = false;
      }
    }
    if (permDenied) {
      showLocationError(); // permission truly denied → show notice strip + fallback
    } else {
      // Permission is still granted but GPS failed technically — show the
      // text fallback silently without the notice strip so the user isn't misled.
      showLocationFallback();
    }
  }
}

if (btnRetryLocation) {
  btnRetryLocation.addEventListener('click', async () => {
    gpsCoords        = null;
    gpsRequested     = false;
    _locationPromise = null;
    await enforceLocation();
  });
}

// ── App init with auth gate ───────────────────────────────────────────────

async function initApp() {
  // Check for a password-reset token in the URL first
  const resetToken = new URLSearchParams(window.location.search).get('reset_token');
  if (resetToken) {
    showAuthOverlay();
    showAuthView(viewReset);
    return;
  }

  loadAuthSession();

  if (!_authToken) {
    showAuthOverlay();
    return;
  }

  // Validate the stored token with the server
  const user = await verifyToken(_authToken);
  if (!user) {
    clearAuthSession();
    showAuthOverlay();
    return;
  }

  // Token is valid — update user in case display_name changed
  _authUser = user;
  try { localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user)); } catch (_) {}

  // T&C gate for returning users
  if (!hasAcceptedTerms()) {
    showAuthOverlay();
    showTermsView('login');
    const acceptOnce = () => {
      markTermsAccepted();
      btnAcceptTerms.removeEventListener('click', acceptOnce);
      hideAuthOverlay();
      updateSidebarUser(user);
      loadHistory();
      renderHistory();
      if (apiHistory.length === 0) showWelcome();
      checkSavedRoute();
      fetchAndRenderHistory();
      _silentGPS();
    };
    btnAcceptTerms.addEventListener('click', acceptOnce);
    return;
  }

  hideAuthOverlay();
  updateSidebarUser(user);
  // Render UI immediately; GPS check runs in background
  fetchAndRenderHistory();
  fetchSubscriptionStatus();  // load tier + quota for returning users
  _silentGPS();
}



// ── DOM refs ──────────────────────────────────────────────────────────────
const chatArea         = document.getElementById('chat-area');
const messageInput     = document.getElementById('message-input');
const btnSend          = document.getElementById('btn-send');
const btnLocation      = document.getElementById('btn-location');
const locationFallback = document.getElementById('location-fallback');
const locationText     = document.getElementById('location-text');

// Status card
const statusCard   = document.getElementById('status-card');
const statusIcon   = document.getElementById('status-icon');
const statusRoute  = document.getElementById('status-route');
const statusDetail = document.getElementById('status-detail');
const btnEditRoute    = document.getElementById('btn-edit-route');
const btnRemoveRoute  = document.getElementById('btn-remove-route');
const btnRefreshRoute = document.getElementById('btn-refresh-route');

// Sidebar / theme / new-chat refs
const btnNewChat            = document.getElementById('btn-new-chat');
const btnThemeToggle        = document.getElementById('btn-theme-toggle');
const btnThemeToggleMobile  = document.getElementById('btn-theme-toggle-mobile');
const btnHamburger          = document.getElementById('btn-hamburger');
const sidebarEl             = document.getElementById('sidebar');
const sidebarOverlay        = document.getElementById('sidebar-overlay');

// ── State ─────────────────────────────────────────────────────────────────
let apiHistory       = [];    // OpenAI-format [{role, content}, …] returned by /chat
let gpsCoords        = null;  // { latitude, longitude } once granted
let gpsRequested     = false; // true after the first send attempt
let isSending        = false;
let activeFetch      = null;  // AbortController for in-flight /chat request
let _locationBlocked = false; // true when location is required but not yet granted
let _locationPromise = null;  // shared in-flight GPS promise — prevents duplicate getCurrentPosition calls
let _currentSessionId = null; // server-assigned ID of the active chat session
let _aiAvailable = null;      // null=unchecked, true=AI ready, false=unavailable

// ── localStorage — history ────────────────────────────────────────────────

function saveHistory() {
  try {
    // Keep last 100 entries (~50 exchanges) to avoid localStorage overflow
    const capped = apiHistory.length > 100 ? apiHistory.slice(-100) : apiHistory;
    localStorage.setItem(HISTORY_KEY, JSON.stringify(capped));
  } catch (_) {
    // localStorage full or unavailable — silently ignore
  }
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    apiHistory = raw ? JSON.parse(raw) : [];
  } catch (_) {
    apiHistory = [];
  }
}

function clearChat() {
  _currentSessionId = null;
  apiHistory = [];
  gpsRequested = false;
  if (activeFetch) { activeFetch.abort(); activeFetch = null; }
  try { localStorage.removeItem(HISTORY_KEY); } catch (_) {}
  chatArea.innerHTML = '';
  // Close sidebar on mobile if open
  if (sidebarEl && sidebarEl.classList.contains('sidebar--open')) toggleSidebar();
  showWelcome();
}

// ── Markdown renderer (no dependencies) ──────────────────────────────────

/**
 * Convert a plain-text AI reply to safe HTML.
 * Escape first, then apply inline rules, then process line-by-line.
 * @param {string} text
 * @returns {string} HTML string (safe for innerHTML)
 */
function parseMarkdown(text) {
  // Step 1: escape HTML special chars
  let s = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Step 2: inline formatting
  s = s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,   '<em>$1</em>')
    .replace(/`(.+?)`/g,     '<code>$1</code>');

  // Step 3: line-by-line block processing
  const lines = s.split('\n');
  let html = '';
  let inUl = false;
  let inOl = false;

  for (const line of lines) {
    const ulMatch = line.match(/^[-•]\s(.*)/);
    const olMatch = line.match(/^\d+\.\s(.*)/);
    if (ulMatch) {
      if (inOl) { html += '</ol>'; inOl = false; }
      if (!inUl) { html += '<ul>'; inUl = true; }
      html += `<li>${ulMatch[1]}</li>`;
    } else if (olMatch) {
      if (inUl) { html += '</ul>'; inUl = false; }
      if (!inOl) { html += '<ol>'; inOl = true; }
      html += `<li>${olMatch[1]}</li>`;
    } else {
      if (inUl) { html += '</ul>'; inUl = false; }
      if (inOl) { html += '</ol>'; inOl = false; }
      if (line.trim() === '') {
        html += '<br>';
      } else {
        html += line + '<br>';
      }
    }
  }
  if (inUl) html += '</ul>';
  if (inOl) html += '</ol>';

  return html;
}

// ── User message metadata helpers ─────────────────────────────────────────

/**
 * The agent prepends GPS and date context to every stored user message:
 *   "[User GPS: lat=43.8, lon=-79.3]\n[Today's date: 20260426]\n\nActual text"
 * This function strips those prefixes out and returns them as structured data
 * so they can be displayed separately in the UI.
 *
 * @param {string} content  Raw content string from history
 * @returns {{ text: string, coords: {latitude:number,longitude:number}|null, dateStr: string|null }}
 */
function parseUserHistoryContent(content) {
  let text = content;
  let coords = null;
  let dateStr = null;

  const gpsMatch = text.match(/^\[User GPS: lat=([-\d.]+), lon=([-\d.]+)\]\n/);
  if (gpsMatch) {
    coords = { latitude: parseFloat(gpsMatch[1]), longitude: parseFloat(gpsMatch[2]) };
    text = text.slice(gpsMatch[0].length);
  }

  const dateMatch = text.match(/^\[Today's date: (\d{8})\]\n\n/);
  if (dateMatch) {
    dateStr = dateMatch[1];
    text = text.slice(dateMatch[0].length);
  }

  return { text, coords, dateStr };
}

/**
 * Format a timestamp string to a human-readable date + time,
 * e.g. "Apr 26, 2026, 3:42 PM".
 * Accepts a full ISO string (from new Date().toISOString()) or a
 * legacy YYYYMMDD string from older history entries.
 * @param {string} ts
 * @returns {string}
 */
function formatHistoryDate(ts) {
  if (!ts) return '';
  let d;
  if (/^\d{8}$/.test(ts)) {
    // Legacy format: YYYYMMDD (date only, no time)
    d = new Date(`${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)}T12:00:00`);
  } else {
    d = new Date(ts);
  }
  if (isNaN(d)) return ts;
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

// ── Render helpers ────────────────────────────────────────────────────────

/**
 * Append a chat bubble and return the inner bubble <div> element.
 * For user bubbles, an optional `meta` object ({ coords, dateStr }) renders
 * GPS coordinates and date as a warm-coloured subline beneath the text.
 *
 * @param {'user'|'assistant'} role
 * @param {string} text
 * @param {{ coords: {latitude:number,longitude:number}|null, dateStr: string|null }|null} [meta]
 * @returns {HTMLElement} The bubble element
 */
function appendBubble(role, text, meta = null) {
  const isUser = role === 'user';
  const rowEl = document.createElement('div');
  rowEl.className = `bubble-row bubble-row--${isUser ? 'user' : 'bot'}`;

  const bubbleEl = document.createElement('div');
  bubbleEl.className = `bubble bubble--${isUser ? 'user' : 'bot'}`;

  if (isUser) {
    const textEl = document.createElement('span');
    textEl.className = 'bubble__text';
    textEl.innerText = text; // innerText — no XSS risk
    bubbleEl.appendChild(textEl);

    if (meta && meta.dateStr) {
      const metaEl = document.createElement('div');
      metaEl.className = 'bubble__meta';
      metaEl.textContent = formatHistoryDate(meta.dateStr);
      bubbleEl.appendChild(metaEl);
    }
  } else {
    bubbleEl.innerHTML = parseMarkdown(text); // safe: HTML-escaped then formatted
  }

  rowEl.appendChild(bubbleEl);
  chatArea.appendChild(rowEl);
  scrollToBottom();
  return bubbleEl;
}

// Progress stage messages shown while waiting for the server
const SEARCH_STAGES = [
  'Searching routes…',
  'Checking live feed…',
  'Getting AI response…',
];
const STAGE_INTERVAL_MS = 2000;   // advance stage every 2 s
const FETCH_TIMEOUT_MS  = 42000;  // hard abort after 42 s

let _stageTimer = null; // holds the setInterval id for stage cycling

function showTyping(initialLabel) {
  if (document.getElementById('typing-row')) return;
  const rowEl = document.createElement('div');
  rowEl.id = 'typing-row';
  rowEl.className = 'bubble-row bubble-row--bot';
  rowEl.setAttribute('aria-label', 'Assistant is typing');

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'bubble bubble--bot bubble--typing';
  bubbleEl.innerHTML =
    '<span class="dot" aria-hidden="true"></span>' +
    '<span class="dot" aria-hidden="true"></span>' +
    '<span class="dot" aria-hidden="true"></span>' +
    `<span class="typing-stage" id="typing-stage">${initialLabel || ''}</span>`;

  rowEl.appendChild(bubbleEl);
  chatArea.appendChild(rowEl);
  scrollToBottom();
}

/** Cycle through SEARCH_STAGES, updating the label inside the typing bubble. */
function startStageTimer() {
  let idx = 0;
  const labelEl = document.getElementById('typing-stage');
  if (labelEl) labelEl.textContent = SEARCH_STAGES[idx];
  _stageTimer = setInterval(() => {
    idx = (idx + 1) % SEARCH_STAGES.length;
    const el = document.getElementById('typing-stage');
    if (el) el.textContent = SEARCH_STAGES[idx];
  }, STAGE_INTERVAL_MS);
}

function stopStageTimer() {
  if (_stageTimer !== null) {
    clearInterval(_stageTimer);
    _stageTimer = null;
  }
}

function removeTyping() {
  stopStageTimer();
  const el = document.getElementById('typing-row');
  if (el) el.remove();
}

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

/** Render stored history into the chat area on page load. */
function renderHistory() {
  chatArea.innerHTML = '';
  for (const msg of apiHistory) {
    if ((msg.role === 'user' || msg.role === 'assistant') && typeof msg.content === 'string' && msg.content) {
      if (msg.role === 'user') {
        const { text, coords, dateStr } = parseUserHistoryContent(msg.content);
        const meta = (coords || dateStr) ? { coords, dateStr } : null;
        appendBubble('user', text, meta);
      } else {
        appendBubble('assistant', msg.content);
      }
    }
  }
}

/** Show welcome screen with suggestion chips when the chat is empty. */
function showWelcome() {
  if (document.getElementById('welcome-screen')) return;

  // Fallback chips shown immediately before /suggestions responds
  const fallbackChips = [
    'What is the DRT bus fare?',
    'How do I contact DRT customer service?',
  ];

  const el = document.createElement('div');
  el.id = 'welcome-screen';
  el.className = 'welcome-screen';
  el.innerHTML =
    '<div class="welcome-screen__icon" aria-hidden="true">🚌</div>' +
    '<h2 class="welcome-screen__heading">Commute Assistant</h2>' +
    '<p class="welcome-screen__sub">Ask about buses, delays, schedules &amp; nearby stops.</p>' +
    '<div class="welcome-chips" role="list" aria-label="Suggested questions">' +
    fallbackChips.map(s => `<button class="chip" role="listitem">${s}</button>`).join('') +
    '</div>';
  chatArea.appendChild(el);
  _bindChips(el);

  // Fetch real context-aware suggestions in background and update chips
  _fetchAndReplaceChips(el);
}

/**
 * Bind click handlers to all .chip buttons inside a welcome screen element.
 * Chips only send if they work locally (AI unavailable) or AI is available.
 */
function _bindChips(el) {
  el.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      messageInput.value = chip.textContent;
      el.remove();
      sendMessage();
    });
  });
}

/**
 * Fetch /suggestions with current GPS coords and replace the chip list.
 */
async function _fetchAndReplaceChips(el) {
  try {
    const lat = gpsCoords ? gpsCoords.latitude  : null;
    const lon = gpsCoords ? gpsCoords.longitude : null;
    const params = new URLSearchParams();
    if (lat !== null) { params.set('lat', lat); params.set('lon', lon); }
    const res = await fetch(`/suggestions?${params}`, { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    const chips = Array.isArray(data.suggestions) ? data.suggestions : [];
    if (chips.length === 0) return;
    _refreshWelcomeChips(el, chips);
  } catch (_) { /* network error — keep fallback chips */ }
}

/**
 * Replace the chip list inside an existing welcome screen element.
 * If no chips array is passed, re-fetches from the server.
 */
function _refreshWelcomeChips(el, chips) {
  if (!el) return;
  const container = el.querySelector('.welcome-chips');
  if (!container) return;

  // If AI is unavailable, keep only local-answerable chips (the suggestions
  // endpoint already returns only those — but guard in case stale chips remain)
  const finalChips = chips || [];
  if (finalChips.length === 0) return;

  container.innerHTML = finalChips
    .map(s => `<button class="chip" role="listitem">${s}</button>`)
    .join('');
  _bindChips(el);
}

// ── Location ──────────────────────────────────────────────────────────────

function showLocationFallback() {
  locationFallback.classList.remove('hidden');
  locationText.focus();
}

/**
 * Request GPS coordinates.
 * - If already obtained, resolves immediately.
 * - If denied or unavailable, shows the text-input fallback and resolves null.
 *
 * @returns {Promise<{latitude: number, longitude: number}|null>}
 */
function getLocation() {
  if (gpsCoords) { return Promise.resolve(gpsCoords); }

  // Return the in-flight promise if a GPS request is already running.
  // This prevents duplicate getCurrentPosition calls when enforceLocation()
  // and sendMessage() race on startup.
  if (_locationPromise) { return _locationPromise; }

  if (!navigator.geolocation) {
    return Promise.resolve(null);
  }

  _locationPromise = new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        gpsCoords = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
        locationFallback.classList.add('hidden');
        _locationPromise = null;
        resolve(gpsCoords);
      },
      (err) => {
        _locationPromise = null;
        resolve(null);
      },
      { timeout: 5000, maximumAge: 300_000 }
    );
  });

  return _locationPromise;
}

/**
 * Silently attempt GPS in the background — absolutely no UI side-effects.
 * If coords resolve, gpsCoords is set (done inside getLocation's success handler).
 * If they don't, nothing happens and skills handle null coords gracefully.
 */
function _silentGPS() {
  if (gpsCoords) return;
  getLocation().then(coords => {
    if (coords) {
      // GPS just resolved — refresh welcome chips to show location-based ones
      const welcomeEl = document.getElementById('welcome-screen');
      if (welcomeEl) _fetchAndReplaceChips(welcomeEl);
    }
  });
}

// ── Send message ──────────────────────────────────────────────────────────

/**
 * Append a timeout message bubble with an "Extend Wait & Retry" button.
 * Clicking the button removes this bubble and retries with a longer timeout.
 *
 * @param {string} message       Error message text
 * @param {object} retryPayload  The /chat payload to retry
 * @param {number} retryTimeout  Timeout (ms) to use for the retry
 */
function appendTimeoutBubble(message, retryPayload, retryTimeout) {
  const rowEl = document.createElement('div');
  rowEl.className = 'bubble-row bubble-row--bot';

  const bubbleEl = document.createElement('div');
  bubbleEl.className = 'bubble bubble--bot';
  bubbleEl.innerHTML = parseMarkdown(message);

  const btn = document.createElement('button');
  btn.className = 'btn--extend-wait';
  btn.textContent = 'Extend Wait & Retry';
  btn.setAttribute('aria-label', 'Extend the wait time and retry the request');
  btn.addEventListener('click', async () => {
    rowEl.remove();
    await retryFetch(retryPayload, retryTimeout);
  });

  bubbleEl.appendChild(btn);
  rowEl.appendChild(bubbleEl);
  chatArea.appendChild(rowEl);
  scrollToBottom();
}

/**
 * Execute the /chat fetch with the given payload and timeout.
 * On timeout, shows an "Extend Wait & Retry" button with a doubled timeout.
 *
 * @param {object} payload    POST body for /chat
 * @param {number} timeoutMs  Milliseconds before aborting the request
 */
async function retryFetch(payload, timeoutMs) {
  isSending = true;
  setSendDisabled(true);
  showTyping();
  startStageTimer();

  const fetchTimeoutId = setTimeout(() => {
    if (activeFetch) { activeFetch.abort(); activeFetch = null; }
  }, timeoutMs);

  try {
    if (activeFetch) activeFetch.abort();
    const controller = new AbortController();
    activeFetch = controller;

    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    clearTimeout(fetchTimeoutId);
    activeFetch = null;

    removeTyping();

    // Parse body once — available for both error and success branches
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (res.status === 401) {
        // JWT expired or invalid — force re-login
        clearAuthSession();
        appendBubble('assistant', 'Your session has expired. Please sign in again.');
        showAuthOverlay();
      } else if (res.status === 422) {
        // Pydantic validation error (e.g. message too long)
        const errDetail = Array.isArray(data.detail)
          ? data.detail.map(e => e.msg || e.message || '').join(' ')
          : (data.detail || 'Your message could not be processed.');
        appendBubble('assistant', `Sorry: ${errDetail}`);
      } else if (res.status === 504) {
        appendTimeoutBubble(
          'The request is taking longer than usual.',
          payload,
          timeoutMs * 2
        );
      } else {
        appendBubble('assistant', `Sorry, something went wrong (${res.status}). Please try again.`);
      }
    } else {
      apiHistory = Array.isArray(data.history) ? data.history : apiHistory;
      saveHistory();
      // Persist the session to server after every reply (upsert)
      saveChatSession([...apiHistory]).then((sid) => {
        if (sid != null) _currentSessionId = sid;
        fetchAndRenderHistory();
      });
      const bubbleEl = appendBubble('assistant', data.reply);
      onAssistantMessage(bubbleEl, data);
    }
  } catch (err) {
    clearTimeout(fetchTimeoutId);
    removeTyping();
    if (err.name === 'AbortError') {
      appendTimeoutBubble(
        'The request timed out. The service may be busy.',
        payload,
        timeoutMs * 2
      );
    } else {
      appendBubble('assistant', 'Could not reach the server. Please check your connection and try again.');
    }
  }

  isSending = false;
  if (!_locationBlocked) {
    setSendDisabled(false);
    messageInput.focus();
  }
}

async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || isSending) return;

  // Try to get GPS silently in the background — no UI side effects ever.
  _silentGPS();

  // If AI is confirmed unavailable, warn and abort — the chips shown are all
  // local-skill answers, so the user shouldn't be typing free-text queries.
  if (_aiAvailable === false) {
    appendBubble('assistant',
      'AI chat is currently unavailable. Please use one of the quick questions above, or tap **Check again** to retry the AI connection.');
    return;
  }

  isSending = true;
  setSendDisabled(true);
  messageInput.value = '';
  messageInput.style.height = 'auto';

  // Show the loader immediately — user gets visual feedback right on send.
  // retryFetch also calls showTyping() but guards against duplicates, so this is safe.
  showTyping('Getting your location…');
  startStageTimer();

  // Always use the latest cached coords; refresh if we don't have them yet.
  // This handles: first send, GPS cache expired, or coords cleared by retry.
  let coords = gpsCoords;
  if (!coords) {
    coords = await getLocation();
    if (coords) {
      gpsCoords = coords;
    } else {
      // GPS failed (timeout or hardware unavailable) even if permission is granted.
      // Quietly show the text fallback so the user can type their area.
      showLocationFallback();
    }
  }
  gpsRequested = true;

  // No hard block here — the agent handles missing coords gracefully.
  // FAQ questions work without GPS; GPS-based skills return a helpful message.
  const manualLocation = locationText.value.trim();
  const finalText = (!coords && manualLocation)
    ? `${text} (I'm near ${manualLocation})`
    : text;

  // Remove welcome screen on first message
  const welcomeScreen = document.getElementById('welcome-screen');
  if (welcomeScreen) welcomeScreen.remove();

  // Build meta for the user bubble: ISO timestamp (date + time)
  const nowISO = new Date().toISOString();
  appendBubble('user', text, { coords, dateStr: nowISO });

  const payload = {
    message: finalText,
    history: apiHistory,
    ...(coords && { latitude: coords.latitude, longitude: coords.longitude }),
  };

  await retryFetch(payload, FETCH_TIMEOUT_MS);

  messageInput.style.height = 'auto';
}

/**
 * Render a row of tappable suggestion chips below a bubble.
 * Clicking a chip fills the input and submits it immediately.
 *
 * @param {HTMLElement} bubbleEl   The assistant bubble element
 * @param {string[]}    suggestions  List of predefined query strings
 */
function renderSuggestions(bubbleEl, suggestions) {
  if (!suggestions || suggestions.length === 0) return;

  const container = document.createElement('div');
  container.className = 'welcome-chips suggestions-chips';
  container.setAttribute('role', 'list');
  container.setAttribute('aria-label', 'Suggested questions');

  suggestions.forEach((text) => {
    const chip = document.createElement('button');
    chip.className = 'chip';
    chip.type = 'button';
    chip.textContent = text;
    chip.setAttribute('role', 'listitem');
    chip.addEventListener('click', () => {
      // Remove chips so user can't double-send
      container.remove();
      messageInput.value = text;
      messageInput.focus();
      // Auto-submit
      sendMessage();
    });
    container.appendChild(chip);
  });

  bubbleEl.appendChild(container);
}

/**
 * Hook called after every assistant reply bubble is rendered.
 * 1. Shows suggestion chips when the response includes an offline fallback.
 * 2. Shows an inline "Save as my regular route" button when the reply
 *    looks like a route result (contains a Route number pattern).
 *
 * @param {HTMLElement} bubbleEl  The assistant bubble element
 * @param {object}      data      Full /chat response payload
 */
// eslint-disable-next-line no-unused-vars
function onAssistantMessage(bubbleEl, data) {
  // --- Offline fallback suggestions ---
  if (Array.isArray(data.suggestions) && data.suggestions.length > 0) {
    renderSuggestions(bubbleEl, data.suggestions);
    return; // Don't also show save-route widget on a fallback message
  }

  const text = bubbleEl.innerText || '';
  // Detect route-like replies: "Route 110", "route 15B", "Bus 916", etc.
  const routeMatch = text.match(/\b(?:Route|Bus)\s+([A-Z0-9]{1,5})\b/i);
  if (!routeMatch) return;

  // Don't offer to save when the reply is a failure / no-result message
  const isNegativeReply = /couldn't find|could not find|no trips|no service|not found|unable to find|no results|no scheduled|no buses|don't have|do not have|sorry/i.test(text);
  if (isNegativeReply) return;

  const detectedRouteLabel = `Route ${routeMatch[1].toUpperCase()}`;

  // Don't show a second button if card is already showing this route
  const saved = loadSavedRoute();
  if (saved && saved.label === detectedRouteLabel) return;

  // Build the inline save widget
  const wrapper = document.createElement('div');
  wrapper.className = 'save-route-widget';

  // Collapsed state: single "Save as my regular route" button
  const btnSave = document.createElement('button');
  btnSave.className = 'btn--save-route';
  btnSave.textContent = 'Save as my regular route';
  wrapper.appendChild(btnSave);

  // Expanded state: mini-form (hidden initially)
  const form = document.createElement('div');
  form.className = 'save-route-form hidden';

  const labelInput = document.createElement('input');
  labelInput.type = 'text';
  labelInput.className = 'input input--location';
  labelInput.placeholder = 'Route label (e.g. Route 110)';
  labelInput.value = detectedRouteLabel;
  labelInput.setAttribute('aria-label', 'Route label');

  const stopInput = document.createElement('input');
  stopInput.type = 'text';
  stopInput.className = 'input input--location';
  stopInput.placeholder = 'Your stop ID (e.g. 1234)';
  stopInput.setAttribute('aria-label', 'Stop ID');

  const routeIdInput = document.createElement('input');
  routeIdInput.type = 'text';
  routeIdInput.className = 'input input--location';
  routeIdInput.placeholder = 'Route ID (optional, for alerts)';
  routeIdInput.setAttribute('aria-label', 'Route ID');

  const confirmBtn = document.createElement('button');
  confirmBtn.className = 'btn--save-route';
  confirmBtn.textContent = 'Confirm';
  confirmBtn.type = 'button';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn--ghost btn--sm';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.type = 'button';

  const btnRow = document.createElement('div');
  btnRow.className = 'btn-row';
  btnRow.appendChild(confirmBtn);
  btnRow.appendChild(cancelBtn);

  form.appendChild(labelInput);
  form.appendChild(stopInput);
  form.appendChild(routeIdInput);
  form.appendChild(btnRow);
  wrapper.appendChild(form);

  btnSave.addEventListener('click', () => {
    btnSave.classList.add('hidden');
    form.classList.remove('hidden');
    stopInput.focus();
  });

  cancelBtn.addEventListener('click', () => {
    form.classList.add('hidden');
    btnSave.classList.remove('hidden');
  });

  confirmBtn.addEventListener('click', () => {
    const stopId  = stopInput.value.trim();
    const label   = labelInput.value.trim() || detectedRouteLabel;
    const routeId = routeIdInput.value.trim() || null;
    if (!stopId) { stopInput.focus(); return; }
    saveRoute({ stop_id: stopId, route_id: routeId, label });
    wrapper.innerHTML = `<span class="save-confirm">✓ Saved as "${label}"</span>`;
  });

  bubbleEl.appendChild(wrapper);
}

// ── Chat history (server-backed) ──────────────────────────────────────────

const chatHistorySection = document.getElementById('chat-history-section');
const chatHistoryList    = document.getElementById('chat-history-list');

/**
 * POST the current conversation to /chat/history.
 * Only called when there is at least one user message.
 * @param {Array} messages  OpenAI-format [{role, content}, …]
 */
/**
 * POST the current conversation to /chat/history (upsert).
 * Returns the session_id from the server, or null on failure.
 * @param {Array} messages  OpenAI-format [{role, content}, …]
 * @returns {Promise<number|null>}
 */
async function saveChatSession(messages) {
  if (!_authToken || !messages || messages.length === 0) return null;
  const hasUserMsg = messages.some(m => m.role === 'user');
  if (!hasUserMsg) return null;
  try {
    const body = { messages };
    if (_currentSessionId != null) body.session_id = _currentSessionId;
    const res = await fetch('/chat/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const data = await res.json();
      return data.session_id ?? null;
    }
  } catch (_) {
    // Non-critical — silently ignore network errors
  }
  return null;
}

/**
 * GET /chat/history and render sessions in the sidebar.
 */
async function fetchAndRenderHistory() {
  if (!_authToken) return;
  try {
    const res = await fetch('/chat/history', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    renderSidebarHistory(data.sessions || []);
  } catch (_) {}
}

/**
 * Render an array of session objects as clickable cards in the sidebar.
 * @param {Array<{id:number, messages:Array, created_at:number}>} sessions
 */
function renderSidebarHistory(sessions) {
  if (!chatHistorySection || !chatHistoryList) return;

  chatHistoryList.innerHTML = '';

  if (sessions.length === 0) {
    chatHistorySection.classList.add('hidden');
    return;
  }

  sessions.forEach((session) => {
    // Use the first user message as the title
    const firstUser = session.messages.find(m => m.role === 'user');
    let title = 'Chat session';
    if (firstUser && firstUser.content) {
      const { text } = parseUserHistoryContent(firstUser.content);
      title = text.length > 42 ? text.slice(0, 42) + '…' : text;
    }

    // Format the timestamp
    const dateLabel = session.created_at
      ? new Date(session.created_at * 1000).toLocaleString(undefined, {
          month: 'short', day: 'numeric',
          hour: 'numeric', minute: '2-digit',
        })
      : '';

    const item = document.createElement('button');
    item.className = 'history-item';
    item.setAttribute('role', 'listitem');
    item.setAttribute('aria-label', `Load chat: ${title}`);
    item.innerHTML =
      `<span class="history-item__title">${escapeHtml(title)}</span>` +
      (dateLabel ? `<span class="history-item__date">${escapeHtml(dateLabel)}</span>` : '');

    item.addEventListener('click', () => loadSessionFromHistory(session));
    chatHistoryList.appendChild(item);
  });

  chatHistorySection.classList.remove('hidden');
}

/**
 * Escape a string for safe use inside innerHTML.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Restore a past session into the chat view.
 * @param {{id:number, messages: Array}} session
 */
function loadSessionFromHistory(session) {
  _currentSessionId = session.id;  // future replies will update this session in-place
  apiHistory = Array.isArray(session.messages) ? session.messages : [];
  saveHistory();
  chatArea.innerHTML = '';
  renderHistory();
  if (apiHistory.length === 0) showWelcome();
  // Close sidebar on mobile
  if (sidebarEl && sidebarEl.classList.contains('sidebar--open')) toggleSidebar();
}

// ── Saved route — localStorage ────────────────────────────────────────────

/**
 * @typedef {{ stop_id: string, route_id: string|null, label: string }} SavedRoute
 */

/** @returns {SavedRoute|null} */
function loadSavedRoute() {
  try {
    const raw = localStorage.getItem(ROUTE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

/**
 * Persist a route and refresh the status card.
 * @param {SavedRoute} route
 */
function saveRoute(route) {
  try { localStorage.setItem(ROUTE_KEY, JSON.stringify(route)); } catch (_) {}
  checkSavedRoute();
}

/** Remove saved route and hide the status card. */
function removeSavedRoute() {
  try { localStorage.removeItem(ROUTE_KEY); } catch (_) {}
  statusCard.classList.add('hidden');
  statusCard.removeAttribute('data-status');
}

// ── Status card ───────────────────────────────────────────────────────────

/**
 * Update the status card DOM.
 * @param {string} label      Route display name
 * @param {string} detailText Line below the route name
 * @param {'on_time'|'late'|'early'|'no_data'} statusKey
 */
function updateStatusCard(label, detailText, statusKey) {
  const icons = { on_time: '🟢', late: '🔴', early: '🟡', no_data: '🚌' };
  statusIcon.textContent   = icons[statusKey] ?? '🚌';
  statusRoute.textContent  = label;
  statusDetail.textContent = detailText;
  statusCard.setAttribute('data-status', statusKey);
  statusCard.classList.remove('hidden');
}

/**
 * Load the saved route from localStorage, call /delays + /alerts, and
 * refresh the status card. Safe to call on page load (no-ops if no route saved).
 */
async function checkSavedRoute() {
  const route = loadSavedRoute();
  if (!route) { statusCard.classList.add('hidden'); return; }

  updateStatusCard(route.label, 'Checking…', 'no_data');

  const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const _hdrs = { ...authHeaders() };

  try {
    const [delayRes, alertRes] = await Promise.all([
      fetch(`/delays/${encodeURIComponent(route.stop_id)}?date=${today}`, { headers: _hdrs }),
      route.route_id
        ? fetch(`/alerts?route_id=${encodeURIComponent(route.route_id)}`, { headers: _hdrs })
        : Promise.resolve(null),
    ]);

    // ── Alerts take priority in the detail line ─────────────────────────
    let alertText = null;
    if (alertRes && alertRes.ok) {
      const alertData = await alertRes.json();
      // Only surface alerts when the feature is available (feed URL is live)
      if (alertData.available && alertData.count > 0) {
        const first = alertData.alerts[0];
        alertText = first.header || 'Service alert active';
      }
    }

    // ── Delay status ────────────────────────────────────────────────────
    if (!delayRes.ok) {
      // 404 = no scheduled trips today, or stop not found
      const detail = alertText ?? (delayRes.status === 404 ? 'No trips scheduled today' : 'Could not load delays');
      updateStatusCard(route.label, detail, alertText ? 'late' : 'no_data');
      return;
    }

    const delayData = await delayRes.json();
    const trips = delayData.trips ?? [];

    // Filter to the saved route_id if we have one; otherwise use first trip
    const relevant = route.route_id
      ? trips.filter(t => t.route_id === route.route_id)
      : trips;

    const trip = relevant[0] ?? trips[0];

    if (!trip) {
      updateStatusCard(route.label, alertText ?? 'No trips scheduled today', 'no_data');
      return;
    }

    if (alertText) {
      updateStatusCard(route.label, alertText, 'late');
      return;
    }

    const statusKey = trip.status ?? 'no_data';
    const delaySec  = trip.delay_seconds;
    let detail;

    if (statusKey === 'on_time') {
      detail = `On time — next at ${formatTime(trip.scheduled_arrival)}`;
    } else if (statusKey === 'late' && delaySec != null) {
      const mins = Math.round(delaySec / 60);
      detail = `${mins} min delay — next at ${formatTime(trip.scheduled_arrival)}`;
    } else if (statusKey === 'early' && delaySec != null) {
      const mins = Math.abs(Math.round(delaySec / 60));
      detail = `Running ${mins} min early — next at ${formatTime(trip.scheduled_arrival)}`;
    } else if (statusKey === 'canceled') {
      detail = `Trip canceled — ${formatTime(trip.scheduled_arrival)} departure`;
    } else {
      detail = `Next at ${formatTime(trip.scheduled_arrival)} — no RT data`;
    }

    updateStatusCard(route.label, detail, statusKey === 'canceled' ? 'late' : statusKey);

  } catch (_) {
    updateStatusCard(route.label, 'Could not load status', 'no_data');
  }
}

/** Format "HH:MM:SS" (may be >24 h) to a human "H:MM AM/PM" string. */
function formatTime(hhmmss) {
  if (!hhmmss) return '—';
  const parts = hhmmss.split(':').map(Number);
  let hours = parts[0] % 24;
  const minutes = parts[1] ?? 0;
  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12 || 12;
  return `${hours}:${String(minutes).padStart(2, '0')} ${ampm}`;
}

// ── Theme & sidebar ───────────────────────────────────────────────────────

const THEME_ICON_DARK  = '☀️';  // shown when in dark mode (click to go light)
const THEME_ICON_LIGHT = '🌙'; // shown when in light mode (click to go dark)

function _applyThemeIcons(theme) {
  const icon = theme === 'dark' ? THEME_ICON_DARK : THEME_ICON_LIGHT;
  if (btnThemeToggle)       btnThemeToggle.textContent = icon;
  if (btnThemeToggleMobile) btnThemeToggleMobile.textContent = icon;
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem(THEME_KEY, next); } catch (_) {}
  _applyThemeIcons(next);
}

function toggleSidebar() {
  sidebarEl.classList.toggle('sidebar--open');
  sidebarOverlay.classList.toggle('active');
  const isOpen = sidebarEl.classList.contains('sidebar--open');
  if (btnHamburger) btnHamburger.setAttribute('aria-expanded', String(isOpen));
}

// ── Status card button handlers ───────────────────────────────────────────

btnEditRoute.addEventListener('click', () => {
  const route = loadSavedRoute();
  if (!route) return;

  // Reuse the same inline form pattern, injected below the status card
  // Remove any existing edit form first
  const existing = document.getElementById('edit-route-form');
  if (existing) { existing.remove(); return; }

  const form = document.createElement('div');
  form.id = 'edit-route-form';
  form.className = 'route-edit-inline';

  const mkInput = (placeholder, value, ariaLabel) => {
    const el = document.createElement('input');
    el.type = 'text';
    el.className = 'input input--location';
    el.placeholder = placeholder;
    el.value = value ?? '';
    el.setAttribute('aria-label', ariaLabel);
    return el;
  };

  const labelInput   = mkInput('Route label', route.label, 'Route label');
  const stopInput    = mkInput('Stop ID', route.stop_id, 'Stop ID');
  const routeIdInput = mkInput('Route ID (optional)', route.route_id ?? '', 'Route ID');

  const saveBtn = document.createElement('button');
  saveBtn.className = 'btn--save-route';
  saveBtn.textContent = 'Save changes';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'btn btn--ghost btn--sm';
  cancelBtn.textContent = 'Cancel';

  const btnRow = document.createElement('div');
  btnRow.className = 'btn-row';
  btnRow.appendChild(saveBtn);
  btnRow.appendChild(cancelBtn);

  form.appendChild(labelInput);
  form.appendChild(stopInput);
  form.appendChild(routeIdInput);
  form.appendChild(btnRow);

  statusCard.insertAdjacentElement('afterend', form);
  labelInput.focus();

  saveBtn.addEventListener('click', () => {
    const stopId  = stopInput.value.trim();
    const label   = labelInput.value.trim() || route.label;
    const routeId = routeIdInput.value.trim() || null;
    if (!stopId) { stopInput.focus(); return; }
    saveRoute({ stop_id: stopId, route_id: routeId, label });
    form.remove();
  });

  cancelBtn.addEventListener('click', () => form.remove());
});

btnRemoveRoute.addEventListener('click', () => {
  removeSavedRoute();
  const editForm = document.getElementById('edit-route-form');
  if (editForm) editForm.remove();
});

if (btnRefreshRoute) btnRefreshRoute.addEventListener('click', () => checkSavedRoute());

function setSendDisabled(disabled) {
  btnSend.disabled = disabled;
  btnSend.setAttribute('aria-disabled', String(disabled));
  messageInput.disabled = disabled;
}

// ── Event listeners ───────────────────────────────────────────────────────

btnSend.addEventListener('click', sendMessage);

messageInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Textarea auto-resize
messageInput.addEventListener('input', () => {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
});

// Location button: re-trigger GPS (or show fallback if unavailable)
btnLocation.addEventListener('click', async () => {
  gpsCoords        = null;
  gpsRequested     = false;
  _locationPromise = null;
  await enforceLocation();
});

// New chat, theme, hamburger
if (btnNewChat) btnNewChat.addEventListener('click', clearChat);
if (btnThemeToggle) btnThemeToggle.addEventListener('click', toggleTheme);
if (btnThemeToggleMobile) btnThemeToggleMobile.addEventListener('click', toggleTheme);
if (btnHamburger) btnHamburger.addEventListener('click', toggleSidebar);
if (sidebarOverlay) sidebarOverlay.addEventListener('click', toggleSidebar);

// ── Monetization state ────────────────────────────────────────────────────

let _userTier          = 'free';   // 'free' | 'premium'
let _queriesUsedToday  = 0;
let _queriesRemaining  = 3;
let _pendingAdTokenId  = null;     // token_id returned by POST /ads/token
let _adCountdownTimer  = null;     // setInterval handle for the countdown

// ── Subscription status ───────────────────────────────────────────────────

async function fetchSubscriptionStatus() {
  if (!_authToken) return;
  try {
    const res = await fetch('/subscription/status', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    _userTier         = data.tier            || 'free';
    _queriesUsedToday = data.queries_used_today ?? 0;
    _queriesRemaining = data.queries_remaining  ?? 0;
    _applySubscriptionUI();
  } catch (_) { /* non-critical */ }
}

function _applySubscriptionUI() {
  const counter = document.getElementById('query-counter');
  const banner  = document.getElementById('ad-banner');

  if (_userTier === 'premium') {
    if (counter) counter.classList.add('hidden');
    if (banner)  banner.classList.add('hidden');
    // Show manage subscription button in upgrade modal if it's open
    const managBtn = document.getElementById('btn-manage-subscription');
    if (managBtn) managBtn.classList.remove('hidden');
    const upgradeBtn = document.getElementById('btn-start-checkout');
    if (upgradeBtn) upgradeBtn.classList.add('hidden');
    return;
  }

  // Free user — show query counter
  if (counter) {
    const label = document.getElementById('queries-used-label');
    if (label) label.textContent = `${_queriesUsedToday} / 3 free queries used today`;
    counter.classList.remove('hidden');
  }

  // Show ad banner for free users (AdSense will fill it when configured)
  if (banner) {
    banner.classList.remove('hidden');
    banner.removeAttribute('aria-hidden');
    // Push AdSense ad into the banner slot (no-op if already pushed or not configured)
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (_) {}
  }
}

// ── Ad Modal ──────────────────────────────────────────────────────────────

const adModal        = document.getElementById('ad-modal');
const adCountdownEl  = document.getElementById('ad-countdown');
const adModalClose   = document.getElementById('ad-modal-close');

function showAdModal(minSeconds, onComplete) {
  if (!adModal) { onComplete(); return; }

  let remaining = minSeconds;
  adModal.classList.remove('hidden');

  if (adCountdownEl) adCountdownEl.textContent = remaining;
  if (adModalClose)  { adModalClose.disabled = true; adModalClose.setAttribute('aria-disabled', 'true'); }

  // Push AdSense ad into the modal slot (once)
  try {
    const ins = document.getElementById('ad-modal-ins');
    if (ins && !ins.dataset.adsbygoogleStatus) {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    }
  } catch (_) {}

  _adCountdownTimer = setInterval(() => {
    remaining -= 1;
    if (adCountdownEl) adCountdownEl.textContent = remaining;
    if (remaining <= 0) {
      clearInterval(_adCountdownTimer);
      _adCountdownTimer = null;
      if (adModalClose) {
        adModalClose.disabled = false;
        adModalClose.removeAttribute('aria-disabled');
      }
    }
  }, 1000);

  // Wire up the close button for this invocation
  const handleClose = () => {
    hideAdModal();
    adModalClose.removeEventListener('click', handleClose);
    onComplete();
  };
  if (adModalClose) adModalClose.addEventListener('click', handleClose);
}

function hideAdModal() {
  if (!adModal) return;
  adModal.classList.add('hidden');
  if (_adCountdownTimer) { clearInterval(_adCountdownTimer); _adCountdownTimer = null; }
  if (adModalClose) { adModalClose.disabled = true; adModalClose.setAttribute('aria-disabled', 'true'); }
}

// Upgrade from ad modal
const btnUpgradeFromAd = document.getElementById('btn-upgrade-from-ad');
if (btnUpgradeFromAd) btnUpgradeFromAd.addEventListener('click', () => { hideAdModal(); openUpgradeModal(); });

// ── Upgrade Modal ─────────────────────────────────────────────────────────

const upgradeModal   = document.getElementById('upgrade-modal');
const upgradeError   = document.getElementById('upgrade-error');
const btnCloseUpgrade = document.getElementById('btn-upgrade-modal-close');
const btnStartCheckout = document.getElementById('btn-start-checkout');
const btnManageSub     = document.getElementById('btn-manage-subscription');
const btnUpgradeFromCounter = document.getElementById('btn-upgrade-from-counter');

console.log('[upgrade] Button references:');
console.log('[upgrade]   upgradeModal:', upgradeModal ? 'found' : 'NOT FOUND');
console.log('[upgrade]   btnStartCheckout:', btnStartCheckout ? 'found' : 'NOT FOUND');
console.log('[upgrade]   btnManageSub:', btnManageSub ? 'found' : 'NOT FOUND');
console.log('[upgrade]   btnUpgradeFromCounter:', btnUpgradeFromCounter ? 'found' : 'NOT FOUND');

function openUpgradeModal() {
  console.log('[upgrade] openUpgradeModal called');
  if (!upgradeModal) {
    console.warn('[upgrade] upgradeModal not found!');
    return;
  }
  upgradeModal.classList.remove('hidden');
  _clearUpgradeError();
  // Sync checkout/manage button visibility with current tier
  if (_userTier === 'premium') {
    if (btnStartCheckout) btnStartCheckout.classList.add('hidden');
    if (btnManageSub)     btnManageSub.classList.remove('hidden');
  } else {
    if (btnStartCheckout) btnStartCheckout.classList.remove('hidden');
    if (btnManageSub)     btnManageSub.classList.add('hidden');
  }
  console.log('[upgrade] Modal opened, tier:', _userTier);
}

function closeUpgradeModal() {
  if (!upgradeModal) return;
  upgradeModal.classList.add('hidden');
}

function _clearUpgradeError() {
  if (upgradeError) { upgradeError.textContent = ''; upgradeError.classList.add('hidden'); }
}

function _showUpgradeError(msg) {
  if (upgradeError) { upgradeError.textContent = msg; upgradeError.classList.remove('hidden'); }
}

if (btnCloseUpgrade)         btnCloseUpgrade.addEventListener('click', closeUpgradeModal);
if (btnUpgradeFromCounter) {
  console.log('[upgrade] Attaching click handler to btnUpgradeFromCounter (sidebar button)');
  btnUpgradeFromCounter.addEventListener('click', () => {
    console.log('[upgrade] Sidebar upgrade button clicked! Opening modal...');
    openUpgradeModal();
  });
} else {
  console.warn('[upgrade] btnUpgradeFromCounter NOT FOUND - sidebar button will not work!');
}

// Close on backdrop click
if (upgradeModal) {
  upgradeModal.addEventListener('click', (e) => {
    if (e.target === upgradeModal) closeUpgradeModal();
  });
}

if (btnStartCheckout) {
  console.log('[upgrade] Attaching click handler to btnStartCheckout');
  btnStartCheckout.addEventListener('click', async () => {
    console.log('[checkout] Button clicked! Starting checkout flow...');
    btnStartCheckout.disabled = true;
    btnStartCheckout.textContent = 'Please wait…';
    _clearUpgradeError();
    try {
      console.log('[checkout] Fetching /subscription/checkout...');
      const res  = await fetch('/subscription/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
      });
      console.log('[checkout] Response status:', res.status);
      const data = await res.json().catch(() => ({}));
      console.log('[checkout] Response data:', data);
      
      if (!res.ok) {
        // Handle "already subscribed" error
        if (data.error === 'already_subscribed') {
          console.log('[checkout] User already has active subscription');
          _showUpgradeError(data.message || 'You already have an active Premium subscription.');
          // Refresh status to ensure UI matches
          await fetchSubscriptionStatus();
        } else {
          _showUpgradeError(data.detail || 'Could not start checkout. Please try again.');
        }
      } else {
        console.log('[checkout] Opened Stripe checkout at:', data.checkout_url);
        // Start polling for subscription status in background (fallback for redirect issues)
        startCheckoutPolling();
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      console.error('[checkout] Error:', err);
      _showUpgradeError('Could not reach the server. Please try again.');
    } finally {
      btnStartCheckout.disabled = false;
      btnStartCheckout.textContent = 'Upgrade Now';
    }
  });
} else {
  console.warn('[upgrade] btnStartCheckout NOT FOUND - event handler not attached!');
}

if (btnManageSub) {
  btnManageSub.addEventListener('click', async () => {
    btnManageSub.disabled = true;
    btnManageSub.textContent = 'Opening portal…';
    _clearUpgradeError();
    try {
      const res  = await fetch('/subscription/portal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        _showUpgradeError(data.detail || 'Could not open billing portal.');
      } else {
        window.location.href = data.portal_url;
      }
    } catch (_) {
      _showUpgradeError('Could not reach the server. Please try again.');
    } finally {
      btnManageSub.disabled = false;
      btnManageSub.textContent = 'Manage Subscription';
    }
  });
}

// Polling for subscription status after checkout
// This is a fallback for cases where Stripe redirect doesn't work
function startCheckoutPolling() {
  console.log('[polling] Starting subscription status polling (fallback for redirect)');
  let pollCount = 0;
  const maxPolls = 120;  // 10 minutes max (120 * 5 seconds)
  
  const pollInterval = setInterval(async () => {
    pollCount++;
    try {
      // First, try to verify payment (queries Stripe and upgrades if subscription found)
      console.log(`[polling] Poll #${pollCount}: Calling verify-payment...`);
      const verifyRes = await fetch('/subscription/verify-payment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() }
      });
      const verifyData = await verifyRes.json().catch(() => ({}));
      console.log(`[polling] verify-payment result:`, verifyData);
      
      // Then check current status
      const statusRes = await fetch('/subscription/status', {
        headers: authHeaders()
      });
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        console.log(`[polling] Poll #${pollCount}: tier=${statusData.tier}`);
        
        if (statusData.tier === 'premium') {
          clearInterval(pollInterval);
          console.log('[polling] ✅ User upgraded to premium!');
          
          // Show success message
          if (!document.getElementById('auth-overlay').classList.contains('hidden')) {
            // Overlay is hidden, app is open
            fetchSubscriptionStatus();
            appendBubble('assistant', '🎉 Welcome to Premium! Payment successful. You now have unlimited queries with no ads.');
            closeUpgradeModal();
          }
          return;
        }
      }
    } catch (err) {
      console.warn(`[polling] Poll #${pollCount} failed:`, err.message);
    }
    
    if (pollCount >= maxPolls) {
      clearInterval(pollInterval);
      console.warn('[polling] Max polls reached. Payment verification timed out.');
    }
  }, 5000);  // Poll every 5 seconds
}

// Handle post-checkout redirect URL parameters
// This function is called AFTER auth is loaded to ensure token is available
function handleCheckoutReturn() {
  console.log('[checkout] handleCheckoutReturn called');
  console.log('[checkout] Current URL:', window.location.href);
  const params = new URLSearchParams(window.location.search);
  console.log('[checkout] URL params:', Array.from(params.entries()));
  
  if (params.has('checkout')) {
    console.log('[checkout] ✅ Detected checkout redirect:', params.get('checkout'));
    window.history.replaceState({}, '', '/');  // clean URL
    if (params.get('checkout') === 'success') {
      console.log('[checkout] ✅ Status is SUCCESS - calling verify-payment');
      // First: verify payment with backend (this upgrades user if payment succeeded)
      fetch('/subscription/verify-payment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
      })
        .then(r => {
          console.log('[checkout] ✅ verify-payment response:', r.status);
          return r.json();
        })
        .then(data => {
          console.log('[checkout] ✅ verify-payment data:', data);
        })
        .catch(err => console.warn('[checkout] ❌ Payment verification error:', err))
        .finally(() => {
          // Then: re-fetch status to show correct tier
          fetchSubscriptionStatus().then(() => {
            if (_userTier === 'premium') {
              appendBubble('assistant', '🎉 Welcome to Premium! You now have unlimited queries with no ads.');
            } else {
              appendBubble('assistant', '✅ Payment received! Your account will upgrade shortly.');
            }
          });
        });
    } else {
      console.log('[checkout] Status is not success:', params.get('checkout'));
    }
  } else {
    console.log('[checkout] No checkout parameter in URL');
  }
}

// ── Ad-gated sendMessage override ────────────────────────────────────────
// We wrap the original sendMessage so free users go through the ad flow first.

const _originalSendMessage = sendMessage;

// Replace sendMessage globally with the ad-gated version
// eslint-disable-next-line no-global-assign
sendMessage = async function adGatedSendMessage() {
  // Premium users and unauthenticated users skip the gate entirely
  if (_userTier === 'premium' || !_authToken) {
    return _originalSendMessage();
  }

  const text = messageInput.value.trim();
  if (!text || isSending) return;

  // Step 1: Request an ad token — this also validates the daily quota server-side
  let tokenData;
  try {
    const res = await fetch('/ads/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
    });
    tokenData = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (res.status === 402 || (tokenData.detail && tokenData.detail.reason === 'quota_exceeded')) {
        // Quota exceeded — show the upgrade modal
        const msg = (tokenData.detail && tokenData.detail.message)
          ? tokenData.detail.message
          : `You've used your 3 free queries for today.`;
        appendBubble('assistant',
          `${msg}\n\nUpgrade to Premium for unlimited access, or come back tomorrow.`);
        openUpgradeModal();
        return;
      }
      appendBubble('assistant', 'Could not start the ad flow. Please try again.');
      return;
    }
  } catch (_) {
    appendBubble('assistant', 'Could not reach the server. Please check your connection.');
    return;
  }

  _pendingAdTokenId = tokenData.token_id;
  const minSeconds  = tokenData.min_ad_seconds || 12;

  // Step 2: Disable input and build the payload while the ad plays.
  isSending = true;
  setSendDisabled(true);
  messageInput.value = '';
  messageInput.style.height = 'auto';

  _silentGPS();
  let coords = gpsCoords;
  if (!coords) { coords = await getLocation(); if (coords) gpsCoords = coords; }

  const manualLocation = locationText.value.trim();
  const finalText = (!coords && manualLocation) ? `${text} (I'm near ${manualLocation})` : text;

  const welcomeScreen = document.getElementById('welcome-screen');
  if (welcomeScreen) welcomeScreen.remove();

  const nowISO = new Date().toISOString();
  appendBubble('user', text, { coords, dateStr: nowISO });

  const payload = {
    message: finalText,
    history: apiHistory,
    ...(coords && { latitude: coords.latitude, longitude: coords.longitude }),
  };

  // Step 3: Show the ad modal. When it closes, POST /ads/complete, then fire the AI request.
  // The AI request must come AFTER /ads/complete because the backend validates the token
  // is marked "used" before allowing the chat through.
  showAdModal(minSeconds, async () => {
    // Mark ad as watched on the server — this sets the token to used=1
    let completeOk = false;
    try {
      const completeRes = await fetch('/ads/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ token_id: _pendingAdTokenId }),
      });
      completeOk = completeRes.ok;
    } catch (_) { /* network error */ }

    if (!completeOk) {
      appendBubble('assistant', 'Ad verification failed. Please try sending your message again.');
      isSending = false;
      setSendDisabled(false);
      return;
    }

    // Now send the AI request — token is marked used, backend will accept it
    await _fetchChatWithToken(payload, _pendingAdTokenId);

    // Refresh the quota counter
    fetchSubscriptionStatus();
  });
};

/**
 * Internal: fire a /chat request with the ad token in the header.
 * Returns a Promise that resolves when the response is rendered.
 */
async function _fetchChatWithToken(payload, tokenId) {
  showTyping('Getting your answer…');
  startStageTimer();

  const fetchTimeoutId = setTimeout(() => {
    if (activeFetch) { activeFetch.abort(); activeFetch = null; }
  }, FETCH_TIMEOUT_MS);

  try {
    if (activeFetch) activeFetch.abort();
    const controller = new AbortController();
    activeFetch = controller;

    const headers = {
      'Content-Type': 'application/json',
      ...authHeaders(),
      'X-Ad-Token': tokenId,
    };

    const res = await fetch('/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    clearTimeout(fetchTimeoutId);
    activeFetch = null;
    removeTyping();

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (res.status === 402) {
        const msg = data.detail && data.detail.message
          ? data.detail.message
          : 'Daily free limit reached. Upgrade for unlimited access.';
        appendBubble('assistant', msg);
        openUpgradeModal();
      } else if (res.status === 403) {
        appendBubble('assistant', 'Ad verification failed. Please try again.');
      } else if (res.status === 401) {
        clearAuthSession();
        appendBubble('assistant', 'Your session has expired. Please sign in again.');
        showAuthOverlay();
      } else if (res.status === 504) {
        appendBubble('assistant', 'The request timed out. Please try again.');
      } else {
        appendBubble('assistant', `Something went wrong (${res.status}). Please try again.`);
      }
    } else {
      apiHistory = Array.isArray(data.history) ? data.history : apiHistory;
      saveHistory();
      saveChatSession([...apiHistory]).then((sid) => {
        if (sid != null) _currentSessionId = sid;
        fetchAndRenderHistory();
      });
      const bubbleEl = appendBubble('assistant', data.reply);
      onAssistantMessage(bubbleEl, data);
    }
  } catch (err) {
    clearTimeout(fetchTimeoutId);
    removeTyping();
    if (err.name !== 'AbortError') {
      appendBubble('assistant', 'Could not reach the server. Please check your connection and try again.');
    }
  }

  isSending = false;
  if (!_locationBlocked) {
    setSendDisabled(false);
    messageInput.focus();
  }
}

// New chat / Logout: also refresh subscription status
const _origFinalizeAuth = _finalizeAuthSuccess;

// ── Init ──────────────────────────────────────────────────────────────────
// Script is at end of <body> so the DOM is already fully parsed.

// Apply saved theme (default dark)
(function initTheme() {
  const saved = (() => { try { return localStorage.getItem(THEME_KEY); } catch (_) { return null; } })();
  const theme = saved || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  _applyThemeIcons(theme);
})();

// Auth gate: validate stored token, then load chat (or show login overlay)
initApp().then(() => {
  console.log('[init] App initialized, authToken present:', !!_authToken);
  if (_authToken) {
    console.log('[init] Loading chat history and content');
    loadHistory();
    renderHistory();
    if (apiHistory.length === 0) showWelcome();
    checkSavedRoute();
    console.log('[init] Calling handleCheckoutReturn() to check for ?checkout=success');
    handleCheckoutReturn();  // Check for ?checkout=success AFTER auth is loaded
  }
}).catch(() => {
  console.error('[init] App initialization failed');
  clearAuthSession();
  showAuthOverlay();
});
