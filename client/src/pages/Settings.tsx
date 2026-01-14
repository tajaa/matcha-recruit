import { useState, useMemo, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { settings, setTokens } from '../api/client';

interface PasswordStrength {
  score: number;
  checks: {
    length: boolean;
    uppercase: boolean;
    lowercase: boolean;
    number: boolean;
    special: boolean;
  };
}

function checkPasswordStrength(password: string): PasswordStrength {
  const checks = {
    length: password.length >= 8,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /[0-9]/.test(password),
    special: /[!@#$%^&*(),.?":{}|<>]/.test(password),
  };

  const score = Object.values(checks).filter(Boolean).length;
  return { score, checks };
}

function getStrengthLabel(score: number): { label: string; color: string } {
  if (score <= 1) return { label: 'WEAK', color: 'text-red-500' };
  if (score <= 2) return { label: 'FAIR', color: 'text-orange-500' };
  if (score <= 3) return { label: 'GOOD', color: 'text-yellow-500' };
  if (score <= 4) return { label: 'STRONG', color: 'text-white' };
  return { label: 'EXCELLENT', color: 'text-white' };
}

export function Settings() {
  const { user, profile, refreshUser } = useAuth();

  // Profile update state
  const [profileName, setProfileName] = useState('');
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);

  // Email change state
  const [emailPassword, setEmailPassword] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [emailError, setEmailError] = useState('');
  const [emailSuccess, setEmailSuccess] = useState('');
  const [emailLoading, setEmailLoading] = useState(false);

  useEffect(() => {
    if (profile?.name) {
      setProfileName(profile.name);
    }
  }, [profile]);

  // Password strength
  const passwordStrength = useMemo(() => checkPasswordStrength(newPassword), [newPassword]);
  const strengthInfo = useMemo(() => getStrengthLabel(passwordStrength.score), [passwordStrength.score]);

  const inputClasses =
    'w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-zinc-700 focus: transition-all font-mono';

  const handleProfileUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess('');
    setProfileLoading(true);

    try {
      await settings.updateProfile({ name: profileName });
      await refreshUser();
      setProfileSuccess('Profile updated successfully');
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : 'Failed to update profile');
    } finally {
      setProfileLoading(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }

    if (passwordStrength.score < 3) {
      setPasswordError('Password is too weak. Please include uppercase, lowercase, numbers, and special characters.');
      return;
    }

    setPasswordLoading(true);
    try {
      await settings.changePassword(currentPassword, newPassword);
      setPasswordSuccess('Password updated successfully');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'Failed to change password');
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleEmailChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailError('');
    setEmailSuccess('');

    if (!newEmail.includes('@')) {
      setEmailError('Please enter a valid email address');
      return;
    }

    setEmailLoading(true);
    try {
      const response = await settings.changeEmail(emailPassword, newEmail);
      setTokens(response.access_token, response.refresh_token);
      await refreshUser();
      setEmailSuccess('Email updated successfully');
      setEmailPassword('');
      setNewEmail('');
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to change email');
    } finally {
      setEmailLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6 font-mono">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-white mb-2">SETTINGS</h1>
        <p className="text-[10px] tracking-[0.3em] uppercase text-zinc-600">
          Account Configuration
        </p>
      </div>

      {/* Current Account Info */}
      <div className="relative mb-8">
        <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-700" />
        <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-700" />
        <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-700" />
        <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-700" />

        <div className="bg-zinc-900/50 border border-zinc-800 p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-1.5 h-1.5 rounded-full bg-matcha-500 animate-pulse" />
            <h2 className="text-[10px] tracking-[0.2em] uppercase text-zinc-500">
              Current Profile
            </h2>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600">Email</span>
              <span className="text-sm text-white">{user?.email}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[9px] tracking-[0.2em] uppercase text-zinc-600">Role</span>
              <span className="text-sm text-white uppercase tracking-wider">{user?.role}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Personal Information */}
      <div className="relative mb-8">
        <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-700" />
        <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-700" />
        <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-700" />
        <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-700" />

        <div className="bg-zinc-900/50 border border-zinc-800 p-6">
          <h2 className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-6">
            Personal Information
          </h2>

          <form onSubmit={handleProfileUpdate}>
            {profileError && (
              <div className="mb-6 p-3 border border-red-500/30 bg-red-500/5 text-red-400 text-[11px] tracking-wide">
                <span className="text-red-500 mr-2">!</span>
                {profileError}
              </div>
            )}
            {profileSuccess && (
              <div className="mb-6 p-3 border border-zinc-700 bg-matcha-500/5 text-white text-[11px] tracking-wide">
                <span className="text-white mr-2">+</span>
                {profileSuccess}
              </div>
            )}

            <div className="mb-5">
              <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                Display Name
              </label>
              <input
                type="text"
                value={profileName}
                onChange={(e) => setProfileName(e.target.value)}
                required
                className={inputClasses}
                placeholder="Enter your name"
              />
            </div>

            <button
              type="submit"
              disabled={profileLoading}
              className="w-full py-3 bg-matcha-500 text-black text-[11px] tracking-[0.2em] uppercase font-medium hover:bg-matcha-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:"
            >
              {profileLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-black/50 animate-pulse" />
                  Updating
                </span>
              ) : (
                'Update Profile'
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Change Password */}
      <div className="relative mb-8">
        <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-700" />
        <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-700" />
        <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-700" />
        <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-700" />

        <div className="bg-zinc-900/50 border border-zinc-800 p-6">
          <h2 className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-6">
            Update Password
          </h2>

          <form onSubmit={handlePasswordChange}>
            {passwordError && (
              <div className="mb-6 p-3 border border-red-500/30 bg-red-500/5 text-red-400 text-[11px] tracking-wide">
                <span className="text-red-500 mr-2">!</span>
                {passwordError}
              </div>
            )}
            {passwordSuccess && (
              <div className="mb-6 p-3 border border-zinc-700 bg-matcha-500/5 text-white text-[11px] tracking-wide">
                <span className="text-white mr-2">+</span>
                {passwordSuccess}
              </div>
            )}

            <div className="mb-5">
              <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                Current Password
              </label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className={inputClasses}
                placeholder="Enter current password"
              />
            </div>

            <div className="mb-5">
              <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                New Password
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                className={inputClasses}
                placeholder="Enter new password"
              />

              {/* Password Strength Indicator */}
              {newPassword && (
                <div className="mt-4 space-y-3">
                  {/* Strength bar */}
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-1 bg-zinc-800 overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          passwordStrength.score <= 1
                            ? 'bg-red-500'
                            : passwordStrength.score <= 2
                              ? 'bg-orange-500'
                              : passwordStrength.score <= 3
                                ? 'bg-yellow-500'
                                : passwordStrength.score <= 4
                                  ? 'bg-matcha-400'
                                  : 'bg-matcha-500'
                        }`}
                        style={{ width: `${(passwordStrength.score / 5) * 100}%` }}
                      />
                    </div>
                    <span className={`text-[9px] tracking-[0.15em] ${strengthInfo.color}`}>
                      {strengthInfo.label}
                    </span>
                  </div>

                  {/* Requirements checklist */}
                  <div className="grid grid-cols-2 gap-2">
                    <div className={`flex items-center gap-2 text-[9px] tracking-wide ${passwordStrength.checks.length ? 'text-white' : 'text-zinc-600'}`}>
                      <span>{passwordStrength.checks.length ? '+' : '-'}</span>
                      <span>8+ Characters</span>
                    </div>
                    <div className={`flex items-center gap-2 text-[9px] tracking-wide ${passwordStrength.checks.uppercase ? 'text-white' : 'text-zinc-600'}`}>
                      <span>{passwordStrength.checks.uppercase ? '+' : '-'}</span>
                      <span>Uppercase</span>
                    </div>
                    <div className={`flex items-center gap-2 text-[9px] tracking-wide ${passwordStrength.checks.lowercase ? 'text-white' : 'text-zinc-600'}`}>
                      <span>{passwordStrength.checks.lowercase ? '+' : '-'}</span>
                      <span>Lowercase</span>
                    </div>
                    <div className={`flex items-center gap-2 text-[9px] tracking-wide ${passwordStrength.checks.number ? 'text-white' : 'text-zinc-600'}`}>
                      <span>{passwordStrength.checks.number ? '+' : '-'}</span>
                      <span>Number</span>
                    </div>
                    <div className={`flex items-center gap-2 text-[9px] tracking-wide ${passwordStrength.checks.special ? 'text-white' : 'text-zinc-600'}`}>
                      <span>{passwordStrength.checks.special ? '+' : '-'}</span>
                      <span>Special Char</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="mb-6">
              <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                Confirm New Password
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className={inputClasses}
                placeholder="Confirm new password"
              />
              {confirmPassword && newPassword !== confirmPassword && (
                <p className="mt-2 text-[9px] text-red-400 tracking-wide">
                  ! Passwords do not match
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={passwordLoading || passwordStrength.score < 3}
              className="w-full py-3 bg-matcha-500 text-black text-[11px] tracking-[0.2em] uppercase font-medium hover:bg-matcha-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:"
            >
              {passwordLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-black/50 animate-pulse" />
                  Updating
                </span>
              ) : (
                'Update Password'
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Change Email */}
      <div className="relative">
        <div className="absolute -top-2 -left-2 w-4 h-4 border-t border-l border-zinc-700" />
        <div className="absolute -top-2 -right-2 w-4 h-4 border-t border-r border-zinc-700" />
        <div className="absolute -bottom-2 -left-2 w-4 h-4 border-b border-l border-zinc-700" />
        <div className="absolute -bottom-2 -right-2 w-4 h-4 border-b border-r border-zinc-700" />

        <div className="bg-zinc-900/50 border border-zinc-800 p-6">
          <h2 className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-6">
            Update Email
          </h2>

          <form onSubmit={handleEmailChange}>
            {emailError && (
              <div className="mb-6 p-3 border border-red-500/30 bg-red-500/5 text-red-400 text-[11px] tracking-wide">
                <span className="text-red-500 mr-2">!</span>
                {emailError}
              </div>
            )}
            {emailSuccess && (
              <div className="mb-6 p-3 border border-zinc-700 bg-matcha-500/5 text-white text-[11px] tracking-wide">
                <span className="text-white mr-2">+</span>
                {emailSuccess}
              </div>
            )}

            <div className="mb-5">
              <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                New Email Address
              </label>
              <input
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                required
                className={inputClasses}
                placeholder="Enter new email address"
              />
            </div>

            <div className="mb-6">
              <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                Confirm with Password
              </label>
              <input
                type="password"
                value={emailPassword}
                onChange={(e) => setEmailPassword(e.target.value)}
                required
                className={inputClasses}
                placeholder="Enter current password"
              />
            </div>

            <button
              type="submit"
              disabled={emailLoading}
              className="w-full py-3 bg-matcha-500 text-black text-[11px] tracking-[0.2em] uppercase font-medium hover:bg-matcha-400 disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:"
            >
              {emailLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-black/50 animate-pulse" />
                  Updating
                </span>
              ) : (
                'Update Email'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default Settings;
