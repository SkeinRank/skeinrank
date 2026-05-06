import type { AuthUser } from "./types";

export type GovernancePermissions = {
  canManageUsers: boolean;
  canManageProfiles: boolean;
  canManageTerms: boolean;
  canManageAliases: boolean;
  canExportSnapshots: boolean;
};

export function permissionsForUser(user: AuthUser): GovernancePermissions {
  const isAdmin = user.role === "admin";
  const isModerator = user.role === "moderator";

  return {
    canManageUsers: isAdmin,
    canManageProfiles: isAdmin,
    canManageTerms: isAdmin || isModerator,
    canManageAliases: isAdmin || isModerator,
    canExportSnapshots: isAdmin || isModerator,
  };
}
