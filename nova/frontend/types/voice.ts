export interface VoiceTokenResponse {
  server_url: string;
  room_name: string;
  participant_identity: string;
  participant_token: string;
  expires_in: number;
}
