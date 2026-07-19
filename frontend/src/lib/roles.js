// Central role-check helpers for the frontend. Keep in sync with backend/permissions.py.

export const ROLE_LABELS = {
  super_admin: 'Super Admin',
  admin: 'Admin',
  interview_panel: 'Interview Panel',
  vendor: 'Agency / Vendor',
  // legacy aliases (should not appear after migration, but harmless)
  recruiter: 'Admin (legacy)',
  interviewer: 'Interview Panel (legacy)',
};

export function isSuperAdmin(user) {
  return user?.role === 'super_admin';
}

export function isAdminOrHigher(user) {
  // Super admin OR admin. Legacy 'recruiter' also allowed as safety.
  return ['super_admin', 'admin', 'recruiter'].includes(user?.role);
}

export function isInterviewPanel(user) {
  return ['interview_panel', 'interviewer'].includes(user?.role);
}

export function isVendor(user) {
  return user?.role === 'vendor';
}

// True if user has a management surface (jobs list, candidates, interviews).
// Interview panel and vendors have their own scoped views but still see the app shell.
export function canManageJobs(user) {
  return isAdminOrHigher(user);
}
