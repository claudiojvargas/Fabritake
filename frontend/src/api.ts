export type Provider = 'simulated' | 'flow';
export type Notice = { code: string; message: string };
export type Settings = { model: string | null; timeout: number; manual_review: boolean; paid_authorized: boolean };
export type Instance = {
  id: string; name: string; provider: Provider; auth: string; availability: string;
  credits: number | null; credit_source: string | null; checked_at: string | null; error: string | null;
};
export type Media = { video?: string; frame?: string; frame_source?: string };
export type Attempt = {
  id: string; state: string; created_at: string; remote_id: string | null; evidence: string | null;
  files: Media; error: Notice | null; dependencies: { scene_id: string; attempt_id: string }[];
};
export type SceneInput = {
  order: number; title: string; prompt: string; duration: number | null; references: string[];
  continuity: 'previous_final_frame' | 'explicit_reference' | 'none';
};
export type Scene = SceneInput & {
  id: string; state: string; files: Media; stale: boolean; attempts: Attempt[]; error: Notice | null;
  selected_attempt: string | null;
};
export type ProjectInput = {
  title: string; description: string; language: string; duration: number | null; ratio: string;
  provider: Provider; instance_id: string; settings: Settings; references: string[];
};
export type Project = ProjectInput & {
  id: string; slug: string; status: string; updated_at: string; total: number; completed: number;
  folder: string; instance_name: string; error: Notice | null;
};
export type Detail = Project & { scenes: Scene[]; references_available: string[] };
export type EventLog = {
  id: number; at: string; project_id: string | null; scene_id: string | null;
  attempt_id: string | null; instance_id: string | null; event: string; detail: string | null;
};

export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const multipart = data instanceof FormData;
  const reply = await fetch(`/api${path}`, {
    method, headers: { 'X-Fabritake': 'local', ...(data != null && !multipart ? { 'Content-Type': 'application/json' } : {}) },
    body: data == null ? undefined : multipart ? data : JSON.stringify(data),
  });
  if (!reply.ok) {
    const payload = await reply.json().catch(() => null);
    const details = payload?.error?.details?.map((item: {field: string; message: string}) => item.field).join(', ');
    throw new Error(payload?.error ? `${payload.error.message}${details ? ' (' + details + ')' : ''}` : `Resposta do servidor: ${reply.status}`);
  }
  return reply.status === 204 ? undefined as T : await reply.json();
}

export function fileUrl(id: string, path: string, download = false) {
  return `/api/projects/${id}/files/${path.split('/').map(encodeURIComponent).join('/')}${download ? '?download=true' : ''}`;
}

export const states: Record<string,string> = {
  draft: 'Rascunho', pending: 'Pendente', queued: 'Na fila', running: 'Em execução',
  preparing: 'Preparando', submitting: 'Enviando', generating: 'Gerando', saving_frame: 'Salvando frame',
  downloading: 'Baixando', validating: 'Validando', awaiting_review: 'Em revisão',
  completed: 'Concluído', pausing: 'Pausando', paused: 'Pausado', failed: 'Falhou',
  requires_reconciliation: 'Requer conferência', stale: 'Referência desatualizada',
  simulated: 'Simulado', unknown: 'Desconhecido', manual_login: 'Login manual',
  available: 'Disponível', closed: 'Fechado', blocked: 'Bloqueado', diagnostic: 'Diagnóstico',
  manual: 'Intervenção manual',
};
export const events: Record<string,string> = {
  ...states, project_created: 'Projeto criado', project_updated: 'Projeto atualizado',
  project_queued: 'Projeto adicionado à fila', project_paused: 'Projeto pausado', project_completed: 'Projeto concluído',
  scene_saved: 'Cena salva', scene_removed: 'Cena removida', scenes_reordered: 'Cenas reordenadas',
  manifest_imported: 'Projeto importado', pause_requested: 'Pausa solicitada',
  retry_requested: 'Nova tentativa solicitada', continuity_stale: 'Referência desatualizada',
  previous_version_kept: 'Versão anterior mantida', reference_uploaded: 'Referência enviada',
  partial_download_retained: 'Download parcial preservado', instance_open: 'Navegador solicitado',
  instance_check: 'Instância verificada', instance_close: 'Sessão encerrada',
};
export const fmtDate = (date: string) => new Intl.DateTimeFormat('pt-BR', {dateStyle: 'short', timeStyle: 'short'}).format(new Date(date));
export const providerName = (p: Provider) => p === 'simulated' ? 'Simulado' : 'Google Flow';
export const active = (status: string) => ['queued', 'running', 'pausing'].includes(status);
