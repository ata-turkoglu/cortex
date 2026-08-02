/** Boundary for OpenAPI-generated code. Feature code imports from this module only. */
export type ApiClient = { getHealth: () => Promise<{ status: string }> };
export const apiClient: ApiClient = { getHealth: async () => ({ status: "unavailable-until-backend-phase" }) };
