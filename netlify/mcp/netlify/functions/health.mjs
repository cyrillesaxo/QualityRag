export default async () => Response.json({service:"qualityrag-mcp",status:"ready",transport:"streamable-http"});
export const config = {path:"/health"};
