import { useState } from 'react';
import { Activity, ArrowDown, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUp, Check, ChevronRight, CircleAlert, Clapperboard,
  Copy, ExternalLink, FileText, Film, Folder, FolderOpen, Image, Layers3, Monitor, Pause, Pencil, Play, Plus, RefreshCw,
  Search, Square, Trash2, Upload } from 'lucide-react';
import { active, events, fileUrl, fmtDate, providerName, states, type Detail, type EventLog, type Instance, type Media, type Project, type Scene } from './api';
import { Alert, Badge, Empty, Logo, Progress } from './ui';

type Run = (path: string, method?: string, data?: unknown, message?: string) => Promise<boolean>;
export type ProjectAction = 'edit' | 'new-scene' | 'delete' | 'delete-scene' | 'retry' | 'reconcile' | 'edit-scene';

export function ProjectsTable({projects, filtered = false}: {projects: Project[]; filtered?: boolean}) {
  if (!projects.length) return <Empty title={filtered ? 'Nenhum resultado' : 'Nenhum projeto ainda'}>
    {filtered ? 'Tente outro termo ou filtro.' : 'Crie um projeto ou carregue o exemplo para começar.'}</Empty>;
  return <div className="table-wrap"><table className="projects-table">
    <thead><tr><th>Projeto</th><th>Status</th><th>Progresso</th><th>Instância</th><th><span className="sr-only">Abrir</span></th></tr></thead>
    <tbody>{projects.map(project => <tr key={project.id}>
      <td><a className="project-name" href={`#projects/${project.id}`}><span className={`project-icon ${project.provider}`}><Clapperboard size={18}/></span>
      <span><strong>{project.title}</strong><small>{providerName(project.provider)} · {project.ratio}</small></span></a></td>
      <td><Badge state={project.status}/></td><td><div className="table-progress"><Progress done={project.completed} total={project.total}/><span>{project.completed}/{project.total}</span></div></td>
      <td className="instance-column">{project.instance_name}</td><td><a className="icon-button" aria-label={`Abrir ${project.title}`} href={`#projects/${project.id}`}><ChevronRight size={18}/></a></td>
    </tr>)}</tbody></table></div>;
}

export function Dashboard({projects, instances, logs, onNew, onDemo}: {
  projects: Project[]; instances: Instance[]; logs: EventLog[]; onNew: () => void; onDemo: () => void;
}) {
  const done = projects.reduce((total, item) => total + item.completed, 0);
  const total = projects.reduce((sum, item) => sum + item.total, 0);
  const running = projects.filter(item => active(item.status)).length;
  const errors = projects.filter(item => item.error).length;
  const stats = [
    { name: 'Projetos', value: projects.length, caption: 'No espaço de trabalho', Icon: Folder, tone: 'purple' },
    { name: 'Cenas concluídas', value: done, caption: `de ${total} cenas cadastradas`, Icon: Film, tone: 'green' },
    { name: 'Em execução', value: running, caption: errors ? `${errors} com erro` : 'Na fila ou em produção', Icon: Activity, tone: 'blue' },
    { name: 'Instâncias', value: instances.length, caption: `${instances.filter(i => i.availability === 'available').length} disponíveis`, Icon: Monitor, tone: 'amber' },
  ];
  return <>
    <div className="page-heading"><div><h1>Visão geral</h1><p>Acompanhe a produção das suas cenas em um só lugar.</p></div>
    <button className="button primary" onClick={onNew}><Plus size={17}/> Novo projeto</button></div>
    <section className="hero">
      <div className="hero-content"><div className="hero-label"><Clapperboard size={15}/> ESTÚDIO DE CENAS</div>
      <h2>Do prompt ao próximo take.</h2>
      <p>Organize suas cenas, preserve a continuidade visual e mantenha cada clipe pronto para a edição.</p>
      <button className="button hero-button" onClick={onDemo}><Play size={15}/> Experimentar simulação <ArrowRight size={15}/></button></div>
      <div className="hero-art" aria-hidden="true"><div className="hero-ring outer"/><div className="hero-ring inner"/>
        <div className="art-plane back"/><div className="art-plane front"><Logo/></div><i className="art-flare one"/><i className="art-flare two"/></div>
    </section>
    <section className="stats-grid" aria-label="Resumo">{stats.map(({name, value, caption, Icon, tone}) => <article className="stat" key={name}>
      <div className="stat-label"><span className={`stat-icon ${tone}`}><Icon size={18}/></span>{name}</div>
      <strong>{value}</strong><span className="stat-caption">{caption}</span>
    </article>)}</section>
    <div className="overview-grid">
      <section className="panel"><div className="panel-heading"><div><h2>Projetos recentes</h2><p>Acompanhe o progresso dos seus projetos.</p></div>
        <a className="text-link" href="#projects">Ver todos <ArrowRight size={15}/></a></div>
        <ProjectsTable projects={projects.slice(0, 5)}/></section>
      <section className="panel activity-panel"><div className="panel-heading"><div><h2>Atividade recente</h2><p>Eventos da produção local.</p></div><a href="#logs" className="icon-button" aria-label="Ver atividade"><ArrowRight size={17}/></a></div>
        {logs.length === 0 ? <div className="activity-empty"><Activity size={22}/><span>Os eventos aparecerão aqui.</span></div> :
          <ul className="activity-list">{logs.slice(0, 5).map(log => <li key={log.id}><span className="timeline-icon">{log.event.includes('completed') ? <Check size={14}/> : <Activity size={14}/>}</span>
            <span><strong>{events[log.event] ?? log.event}</strong><small>{projects.find(project => project.id === log.project_id)?.title ?? 'Local'} · {fmtDate(log.at)}</small></span></li>)}</ul>}
      </section>
    </div>
  </>;
}

export function Projects({projects, onNew, onImport}: {projects: Project[]; onNew: () => void; onImport: () => void}) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('');
  const visible = projects.filter(item => item.title.toLowerCase().includes(search.toLowerCase()) && (!filter || filter === item.provider));
  return <><div className="page-heading"><div><h1>Projetos</h1><p>Crie e organize suas sequências de cenas.</p></div><div className="actions">
    <button className="button secondary" onClick={onImport}><Upload size={16}/> Importar</button><button className="button primary" onClick={onNew}><Plus size={17}/> Novo projeto</button></div></div>
    <section className="panel"><div className="toolbar"><label className="search"><Search size={17}/><input placeholder="Buscar projetos…" aria-label="Buscar projetos" value={search} onChange={e => setSearch(e.target.value)}/></label>
      <select aria-label="Filtrar provedor" value={filter} onChange={e => setFilter(e.target.value)}><option value="">Todos os provedores</option><option value="simulated">Simulado</option><option value="flow">Google Flow</option></select></div>
      <ProjectsTable projects={visible} filtered={!!(search || filter)}/></section></>;
}

function MediaView({project, files}: {project: Detail; files: Media}) {
  if (!files.video && !files.frame) return null;
  return <div className="media-grid">
    {files.video && <div><div className="media-heading"><span>Clipe MP4</span><a className="icon-button" aria-label="Baixar clipe" href={fileUrl(project.id, files.video, true)}><ArrowDownToLine size={16}/></a></div>
      <video key={files.video} controls preload="metadata" poster={files.frame ? fileUrl(project.id, files.frame) : undefined} src={fileUrl(project.id, files.video)}/></div>}
    {files.frame && <div><div className="media-heading"><span>Frame final {files.frame_source === 'fixture' && '· simulado'}</span><a className="icon-button" aria-label="Baixar frame" href={fileUrl(project.id, files.frame, true)}><ArrowDownToLine size={16}/></a></div>
      <img src={fileUrl(project.id, files.frame)} alt="Frame final da cena"/></div>}
  </div>;
}

export function ProjectDetail({project, run, busy, decide, notify}: {
  project: Detail; busy: boolean; run: Run; decide: (action: ProjectAction, scene?: Scene) => void; notify: (message: string) => void;
}) {
  const [tab, setTab] = useState<'scenes'|'files'>('scenes');
  const [selected, setSelected] = useState('');
  const scene = project.scenes.find(item => item.id === selected) ?? project.scenes[0];
  const running = active(project.status);
  const path = `/projects/${project.id}`;
  const scenePath = scene ? `${path}/scenes/${scene.id}` : '';
  const attempt = scene?.attempts[0];
  const openReview = scene?.state === 'awaiting_review';
  const artifact = openReview ? attempt?.files : scene?.files;
  const canEditScene = !running && !!scene && !['requires_reconciliation','awaiting_review'].includes(scene.state);
  const canReorder = !running && project.scenes.every(item => !item.attempts.length);
  const reorder = (shift: number) => {
    const order = project.scenes.map(item => item.id);
    const index = order.indexOf(scene.id);
    [order[index], order[index + shift]] = [order[index + shift], order[index]];
    void run(`${path}/scenes/order`, 'PUT', {scene_ids: order}, 'Ordem atualizada.');
  };
  return <>
    <a href="#projects" className="back-link"><ArrowLeft size={16}/> Projetos</a>
    <div className="page-heading detail-heading"><div><div className="heading-badges"><Badge state={project.status}/><span className="mode-tag">{providerName(project.provider)}</span></div>
      <h1>{project.title}</h1><p>{project.description || `${project.instance_name} · ${project.ratio} · ${project.language}`}</p></div>
      <div className="actions">
        <button className="button secondary" onClick={() => decide('edit')} disabled={running}><Pencil size={15}/> Editar</button>
        {running ? <button className="button secondary" disabled={busy || project.status === 'pausing'} onClick={() => void run(`${path}/run/pause`)}><Pause size={16}/> Pausar</button>
          : <button className="button primary" disabled={busy || !project.total || project.status === 'completed'} onClick={() => void run(`${path}/run/${project.status === 'paused' ? 'resume' : 'start'}`)}><Play size={16}/>
          {project.status === 'paused' ? 'Retomar' : 'Iniciar geração'}</button>}
      </div></div>
    {project.error && <Alert>{project.error.message}</Alert>}
    {project.provider === 'flow' && <div className="notice"><Monitor size={17}/> Google Flow em diagnóstico. A geração real precisa de validação na interface do provedor.</div>}
    <div className="panel project-summary"><div><span>Progresso</span><strong>{project.completed} de {project.total} cenas</strong></div><Progress done={project.completed} total={project.total}/>
      <div><span>Instância</span><strong>{project.instance_name}</strong></div><div><span>Proporção</span><strong>{project.ratio}</strong></div></div>
    <div className="tabs" aria-label="Detalhes do projeto">
      <button className={tab === 'scenes' ? 'selected' : ''} onClick={() => setTab('scenes')}><Clapperboard size={17}/> Cenas <small>{project.total}</small></button>
      <button className={tab === 'files' ? 'selected' : ''} onClick={() => setTab('files')}><Folder size={17}/> Arquivos</button>
    </div>
    {tab === 'files' ? <section className="panel"><div className="panel-heading"><div><h2>Arquivos do projeto</h2><p>Metadados, referências e mídias selecionadas.</p></div></div>
      <div className="files-content"><div className="folder-line"><code>{project.folder}</code><button className="icon-button" aria-label="Copiar caminho"
        onClick={async () => { try {await navigator.clipboard.writeText(project.folder); notify('Caminho copiado.');} catch {notify('A área de transferência está indisponível.');} }}><Copy size={17}/></button>
        <button className="button secondary" disabled={busy} onClick={() => void run(`${path}/open-folder`)}><FolderOpen size={17}/> Abrir pasta</button></div>
        <div className="actions"><a className="button secondary" href={`/api${path}/export`} download="manifesto.json"><ArrowDownToLine size={16}/> Manifesto JSON</a>
          <a className="button secondary" href={`/api${path}/export?format=markdown`}><ArrowDownToLine size={16}/> Roteiro Markdown</a>
          <label className={`button secondary upload-button ${running || busy ? 'disabled' : ''}`}><Upload size={16}/> Enviar referência<input aria-label="Enviar referência" type="file" accept="image/png,image/jpeg,image/webp"
            disabled={running || busy} onChange={e => {const file = e.target.files?.[0]; if (!file) return; const data = new FormData(); data.set('file', file); void run(`${path}/references`, 'POST', data, 'Referência enviada. Vincule-a nas configurações do projeto ou da cena.'); e.target.value = '';}}/></label></div>
        <ul className="file-list">{['projeto.json','roteiro.md','prompts.md','logs/eventos.jsonl', ...project.references_available, ...project.scenes.flatMap(item => [item.files.video, item.files.frame].filter((entry): entry is string => !!entry))].map(file =>
          <li key={file}><FileText size={17}/><span>{file}</span><a className="icon-button" href={fileUrl(project.id, file, true)} aria-label={`Baixar ${file}`}><ArrowDownToLine size={16}/></a></li>)}</ul>
        <button className="button danger" disabled={running} onClick={() => decide('delete')}><Trash2 size={16}/> Remover projeto</button>
      </div></section> :
      <div className="scene-grid"><section className="panel scene-nav"><div className="panel-heading"><h2>Sequência</h2><button className="icon-button" onClick={() => decide('new-scene')} disabled={running} aria-label="Nova cena"><Plus size={20}/></button></div>
        {!project.scenes.length ? <Empty title="Sem cenas" action={<button className="button secondary" onClick={() => decide('new-scene')}><Plus size={16}/> Adicionar cena</button>}/> :
          <ul>{project.scenes.map(item => <li key={item.id}><button className={scene?.id === item.id ? 'chosen' : ''} onClick={() => setSelected(item.id)}>
            <span className="scene-index">{String(item.order).padStart(2, '0')}</span><span><strong>{item.title}</strong><small>{states[item.stale ? 'stale' : item.state]}</small></span><ChevronRight size={16}/></button></li>)}</ul>}
        {scene && canReorder && project.scenes.length > 1 && <div className="reorder">
          <button className="icon-button" aria-label="Mover cena para cima" disabled={busy || scene.id === project.scenes[0].id} onClick={() => reorder(-1)}><ArrowUp size={16}/></button>
          <button className="icon-button" aria-label="Mover cena para baixo" disabled={busy || scene.id === project.scenes.at(-1)?.id} onClick={() => reorder(1)}><ArrowDown size={16}/></button></div>}
      </section>
      {scene ? <section className="panel scene-content"><div className="panel-heading"><div><Badge state={scene.stale ? 'stale' : scene.state}/><h2>{scene.title}</h2></div>
        <div className="actions"><button className="icon-button" aria-label="Editar cena" disabled={!canEditScene} onClick={() => decide('edit-scene', scene)}><Pencil size={17}/></button>
          <button className="icon-button" aria-label="Remover cena" disabled={!canEditScene || !!scene.attempts.length} onClick={() => decide('delete-scene', scene)}><Trash2 size={17}/></button></div></div>
        <div className="scene-body">
          {scene.error && <Alert>{scene.error.message}</Alert>}
          <h3>Prompt</h3><p className="prompt">{scene.prompt}</p>
          <p className="continuity"><Layers3 size={15}/>{scene.continuity === 'previous_final_frame' ? 'Frame final da cena anterior' : scene.continuity === 'explicit_reference' ? 'Referência específica' : 'Sem continuidade'}{scene.duration ? ` · ${scene.duration} s desejados` : ''}</p>
          {artifact && <MediaView key={openReview ? attempt?.id : scene.selected_attempt} project={project} files={artifact}/>}
          <div className="actions scene-actions">
            {openReview && <><button className="button primary" disabled={busy} onClick={() => void run(`${scenePath}/review`, 'POST', {approve: true}, 'Cena aprovada.')}><Check size={16}/> Aprovar</button>
              <button className="button secondary" disabled={busy} onClick={() => void run(`${scenePath}/review`, 'POST', {approve: false}, 'Tentativa rejeitada.')}>Rejeitar</button></>}
            {!running && ['completed','paused','failed'].includes(scene.state) && <button className="button secondary" disabled={busy} onClick={() => decide('retry', scene)}><RefreshCw size={16}/> {scene.state === 'completed' ? 'Regenerar' : 'Nova tentativa'}</button>}
            {!running && scene.stale && <button className="button secondary" disabled={busy} onClick={() => void run(`${scenePath}/keep`, 'POST', undefined, 'Versão anterior mantida.')}>Manter versão atual</button>}
            {!running && scene.state === 'requires_reconciliation' && <><button className="button secondary" disabled={busy} onClick={() => void run(`${scenePath}/reconcile`, 'POST', {acknowledge: false}, 'Tentativa conferida.')}>Verificar tentativa</button>
              <button className="button secondary" disabled={busy} onClick={() => decide('reconcile', scene)}>Encerrar após conferência</button></>}
          </div>
          {scene.attempts.length > 0 && <div className="attempts"><h3>Tentativas</h3><ul>{scene.attempts.map(item => <li key={item.id}><div><Badge state={item.state}/><small>{fmtDate(item.created_at)} · {item.id.slice(0, 8)} {item.dependencies.length ? '· usa frame anterior' : ''}</small>
            {item.error && <small>{item.error.message}</small>}</div><div className="actions">
            {item.files.video && <a className="icon-button" href={fileUrl(project.id, item.files.video, true)} aria-label="Baixar vídeo desta tentativa"><Film size={16}/></a>}
            {item.files.frame && <a className="icon-button" href={fileUrl(project.id, item.files.frame, true)} aria-label="Baixar frame desta tentativa"><Image size={16}/></a>}</div></li>)}</ul></div>}
        </div></section> : <section className="panel"><Empty title="Monte sua sequência de cenas">Adicione cenas com título, prompt e estratégia de continuidade.</Empty></section>}
      </div>}
  </>;
}

export function Instances({items, onNew, run, busy}: {items: Instance[]; onNew: () => void; run: Run; busy: boolean}) {
  return <><div className="page-heading"><div><h1>Instâncias</h1><p>Gerencie o simulador e os perfis de navegador do Google Flow.</p></div>
    <button className="button primary" onClick={onNew}><Plus size={17}/> Nova instância</button></div>
    {!items.length ? <section className="panel"><Empty title="Nenhuma instância cadastrada" action={<button className="button secondary" onClick={onNew}><Plus size={17}/> Cadastrar instância</button>}>Cadastre um simulador local ou um perfil para diagnóstico do Google Flow.</Empty></section> :
      <div className="instances-grid">{items.map(item => <article className="panel instance-card" key={item.id}><div className="panel-heading">
        <span className="project-icon"><Monitor size={20}/></span><Badge state={item.availability}/></div>
        <div className="instance-body"><h2>{item.name}</h2><p>{providerName(item.provider)}</p><dl>
          <div><dt>Autenticação</dt><dd>{states[item.auth] ?? item.auth}</dd></div>
          <div><dt>Créditos observados</dt><dd>{item.provider === 'simulated' ? 'Dispensa créditos' : item.credits ?? 'Desconhecidos'}{item.credit_source && ` · ${item.credit_source}`}</dd></div>
          <div><dt>Última verificação</dt><dd>{item.checked_at ? fmtDate(item.checked_at) : '—'}</dd></div>
        </dl>{item.error && <p className="instance-note">{item.error}</p>}
        <div className="actions">
          {item.provider === 'flow' && <button className="button primary" disabled={busy} onClick={() => void run(`/instances/${item.id}/open`)}><ExternalLink size={15}/> Abrir navegador</button>}
          <button className="button secondary" disabled={busy} onClick={() => void run(`/instances/${item.id}/check`)}><RefreshCw size={15}/> Verificar</button>
          {item.provider === 'flow' && <button className="button secondary" disabled={busy || item.availability === 'closed'} onClick={() => void run(`/instances/${item.id}/close`)}><Square size={14}/> Fechar</button>}
        </div></div></article>)}</div>}</>;
}

export function ActivityView({logs, projects}: {logs: EventLog[]; projects: Project[]}) {
  const [project, setProject] = useState('');
  const [query, setQuery] = useState('');
  const filtered = logs.filter(log => (!project || log.project_id === project) &&
    `${events[log.event] ?? log.event} ${log.detail ?? ''}`.toLowerCase().includes(query.toLowerCase()));
  return <><div className="page-heading"><div><h1>Atividade</h1><p>Consulte ações do worker, erros e eventos de recuperação.</p></div></div>
    <section className="panel"><div className="toolbar"><label className="search"><Search size={17}/><input value={query} aria-label="Buscar eventos" placeholder="Buscar eventos…" onChange={event => setQuery(event.target.value)}/></label>
      <select aria-label="Filtrar projeto" value={project} onChange={event => setProject(event.target.value)}><option value="">Todos os projetos</option>
        {projects.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div>
      {filtered.length ? <div className="table-wrap"><table className="logs-table"><thead><tr><th>Data e hora</th><th>Evento</th><th>Projeto</th><th>Tentativa</th></tr></thead>
        <tbody>{filtered.map(log => <tr key={log.id}><td>{fmtDate(log.at)}</td><td><strong>{events[log.event] ?? log.event}</strong>{log.detail && <small><CircleAlert size={12}/>{log.detail}</small>}</td>
          <td>{projects.find(item => item.id === log.project_id)?.title ?? '—'}</td><td><code>{log.attempt_id?.slice(0, 8) ?? '—'}</code></td></tr>)}</tbody></table></div> :
        <Empty title="Nenhum evento encontrado">As ações do worker aparecem aqui durante a execução.</Empty>}</section></>;
}
