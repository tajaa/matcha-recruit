import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { settings, setTokens } from '../api/client';
import { Button } from '../components';

export function Settings() {
  const { user, refreshUser } = useAuth();

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

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }

    if (newPassword.length < 8) {
      setPasswordError('Password must be at least 8 characters');
      return;
    }

    setPasswordLoading(true);
    try {
      await settings.changePassword(currentPassword, newPassword);
      setPasswordSuccess('Password changed successfully');
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
      // Update tokens and refresh user data
      setTokens(response.access_token, response.refresh_token);
      await refreshUser();
      setEmailSuccess('Email changed successfully');
      setEmailPassword('');
      setNewEmail('');
    } catch (err) {
      setEmailError(err instanceof Error ? err.message : 'Failed to change email');
    } finally {
      setEmailLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-white mb-8">Account Settings</h1>

      {/* Current Account Info */}
      <div className="bg-zinc-900 rounded-xl p-6 border border-white/5 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Account Information</h2>
        <div className="space-y-2 text-zinc-400">
          <p>
            <span className="text-zinc-500">Email:</span> {user?.email}
          </p>
          <p>
            <span className="text-zinc-500">Role:</span>{' '}
            <span className="capitalize">{user?.role}</span>
          </p>
        </div>
      </div>

      {/* Change Password */}
      <div className="bg-zinc-900 rounded-xl p-6 border border-white/5 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">Change Password</h2>
        <form onSubmit={handlePasswordChange}>
          {passwordError && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {passwordError}
            </div>
          )}
          {passwordSuccess && (
            <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-green-400 text-sm">
              {passwordSuccess}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-zinc-400 mb-2">
              Current Password
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
              placeholder="Enter current password"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-zinc-400 mb-2">
              New Password
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
              placeholder="Enter new password (min 8 characters)"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-zinc-400 mb-2">
              Confirm New Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
              placeholder="Confirm new password"
            />
          </div>

          <Button type="submit" disabled={passwordLoading}>
            {passwordLoading ? 'Changing...' : 'Change Password'}
          </Button>
        </form>
      </div>

      {/* Change Email */}
      <div className="bg-zinc-900 rounded-xl p-6 border border-white/5">
        <h2 className="text-lg font-semibold text-white mb-4">Change Email</h2>
        <form onSubmit={handleEmailChange}>
          {emailError && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {emailError}
            </div>
          )}
          {emailSuccess && (
            <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-green-400 text-sm">
              {emailSuccess}
            </div>
          )}

          <div className="mb-4">
            <label className="block text-sm font-medium text-zinc-400 mb-2">
              New Email
            </label>
            <input
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              required
              className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
              placeholder="Enter new email address"
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-zinc-400 mb-2">
              Confirm with Password
            </label>
            <input
              type="password"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.target.value)}
              required
              className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-matcha-500"
              placeholder="Enter your password to confirm"
            />
          </div>

          <Button type="submit" disabled={emailLoading}>
            {emailLoading ? 'Changing...' : 'Change Email'}
          </Button>
        </form>
      </div>
    </div>
  );
}
