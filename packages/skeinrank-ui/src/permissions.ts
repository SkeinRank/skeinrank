import { areLegacyWriteToolsEnabled } from "./config";
import type { AuthUser } from "./types";

export type GovernancePermissions = {
  canManageUsers: boolean;
  canManageProfiles: boolean;
  canManageTerms: boolean;
  canManageAliases: boolean;
  canExportSnapshots: boolean;
  canCreateSuggestions: boolean;
  canReviewSuggestions: boolean;
  canReadStopLists: boolean;
  canManageStopLists: boolean;
  canReadBindings: boolean;
  canManageBindings: boolean;
  canManageApiTokens: boolean;
  canManageServiceAccounts: boolean;
};

export function permissionsForUser(user: AuthUser): GovernancePermissions {
  const isAdmin = user.role === "admin";
  const isModerator = user.role === "moderator";
  const legacyWriteToolsEnabled = areLegacyWriteToolsEnabled();
  const canUseLegacyGovernanceWrites = legacyWriteToolsEnabled && (isAdmin || isModerator);

  return {
    canManageUsers: isAdmin,
    canManageProfiles: legacyWriteToolsEnabled && isAdmin,
    canManageTerms: canUseLegacyGovernanceWrites,
    canManageAliases: canUseLegacyGovernanceWrites,
    canExportSnapshots: canUseLegacyGovernanceWrites,
    canCreateSuggestions: isAdmin || isModerator || user.role === "contributor",
    canReviewSuggestions: isAdmin || isModerator,
    canReadStopLists: true,
    canManageStopLists: canUseLegacyGovernanceWrites,
    canReadBindings: true,
    canManageBindings: canUseLegacyGovernanceWrites,
    canManageApiTokens: true,
    canManageServiceAccounts: isAdmin,
  };
}
