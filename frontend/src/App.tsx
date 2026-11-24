import { useEffect, useState } from 'react';
import { Activity, ChevronRight, Clapperboard, CircleCheck, Folder, LayoutGrid, Monitor, Radio, X } from 'lucide-react';
import { api, type Detail, type EventLog, type Instance, type Project, type Scene } from './api';
import { Confirmation, ImportForm, InstanceForm, ProjectForm, SceneForm } from './forms';
import { Alert, Logo } from './ui';
import { ActivityView, Dashboard, Instances, ProjectDetail, Projects, type ProjectAction } from './views';

const pages = [
  { path: 'overview', label: 'Visão geral', Icon: LayoutGrid },
  { path: 'projects', label: 'Projetos', Icon: Folder },
  { path: 'instances', label: 'Instâncias', Icon: Monitor },
  { path: 'logs', label: 'Atividade', Icon: Activity },
];
const readHash = () => window.location.hash.slice(1) || 'overview';
type ModalState = {type: 'new' | 'instance' | 'import' | ProjectAction; scene?: Scene};
type Snapshot = { projects: Project[]; instances: Instance[]; logs: EventLog[]; detail: Detail | null };

export function App() {
  const [route, setRoute] = useState(readHash);
  const [snapshot, setSnapshot] = useState<Snapshot>({projects: [], instances: [], logs: [], detail: null});
  const [connection, setConnection] = useState<'connecting'|'online'|'offline'>('connecting');
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loadingError, setLoadingError] = useState('');
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [section, id] = route.split('/');
  const detail = snapshot.detail?.id === id ? snapshot.detail : null;
  const {projects, instances, logs} = snapshot;
  const nav = pages.find(page => page.path === section) ?? pages[0];
  const refresh = () => setRevision(prev => prev + 1);
  async function run(path: string, method = 'POST', data?: unknown, message?: string) {
    setBusy(true);
    setError('');
    try {
      await api(path, method, data);
      refresh();
      if (message) setNotice(message);
      return true;
    } catch (error) {
      setError((error as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const update = () => {
      setRoute(readHash());
      setError('');
      setModal(null);
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  useEffect(() => {
    let ignored = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      const common = await Promise.allSettled([
        api<Project[]>('/projects'), api<Instance[]>('/instances'), api<EventLog[]>('/logs'),
        id && section === 'projects' ? api<Detail>(`/projects/${id}`) : Promise.resolve(null),
      ] as const);
      if (ignored) return;
      const [projects, instances, logs, detail] = common;
      if (projects.status === 'fulfilled' && instances.status === 'fulfilled' && logs.status === 'fulfilled') {
        setSnapshot({projects: projects.value, instances: instances.value, logs: logs.value, detail: detail.status === 'fulfilled' ? detail.value : null});
        setLoadingError(detail.status === 'rejected' ? detail.reason.message : '');
        setConnection('online');
      } else {
        setConnection('offline');
        setLoadingError('Não foi possível conectar ao servidor local do Fabritake.');
      }
      timer = setTimeout(load, 1800);
    }
    void load();
    return () => {ignored = true; clearTimeout(timer);};
  }, [id, section, revision]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4200);
    return () => clearTimeout(timer);
  }, [notice]);

  function projectSaved(project: Detail) {
    setSnapshot(current => ({...current, detail: project}));
    refresh();
    window.location.hash = `projects/${project.id}`;
  }
  async function demo() {
    setBusy(true);
    setError('');
    try {
      const project = await api<Detail>('/demo', 'POST');
      projectSaved(project);
      setNotice('Projeto de exemplo criado. Inicie a geração simulada na próxima tela.');
    } catch (error) {setError((error as Error).message);}
    finally {setBusy(false);}
  }
  const close = () => setModal(null);
  const scene = modal?.scene;
  const base = detail ? `/projects/${detail.id}` : '';
  const scenePath = scene ? `${base}/scenes/${scene.id}` : '';
  const confirm = async (path: string, method: string, payload?: unknown) => {
    await api(path, method, payload);
    refresh();
  };
  return <div className="shell">
    <aside className="sidebar"><a className="brand" href="#overview"><Logo small/><span>Fabritake</span></a>
      <div className="workspace"><span className="workspace-icon"><Clapperboard size={18}/></span><span><strong>Estúdio local</strong><small>Espaço de trabalho</small></span></div>
      <nav aria-label="Navegação principal"><p className="nav-label">ESTÚDIO</p>{pages.map(({path, label, Icon}) =>
        <a key={path} href={`#${path}`} className={nav.path === path ? 'current' : ''} aria-label={label} aria-current={nav.path === path ? 'page' : undefined}>
          <Icon size={18}/><span>{label}</span></a>)}</nav>
      <div className="sidebar-foot"><span className={`status-light ${connection}`}/><span><strong>Servidor local</strong>
        <small>{connection === 'online' ? 'Conectado' : connection === 'offline' ? 'Desconectado' : 'Conectando…'}</small></span></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><a href="#overview">Estúdio local</a><ChevronRight size={14}/>
      {detail ? <><a href="#projects">{nav.label}</a><ChevronRight size={14}/><strong>{detail.title}</strong></> : <strong>{nav.label}</strong>}</div>
      <span className="local-pill"><Radio size={14}/> Ambiente local</span></header>
    <main className="main-content" id="main">
      {loadingError && <Alert>{loadingError}</Alert>}
      {error && <div className="page-error"><Alert>{error}</Alert><button className="icon-button" aria-label="Fechar aviso" onClick={() => setError('')}><X size={17}/></button></div>}
      {nav.path === 'overview' && <Dashboard projects={projects} instances={instances} logs={logs} onNew={() => setModal({type:'new'})}
        onDemo={() => {if (!busy) void demo();}}/>}
      {nav.path === 'projects' && (id ? detail ? <ProjectDetail key={id} project={detail} run={run} busy={busy}
        decide={(type, scene) => setModal({type, scene})} notify={setNotice}/> : !loadingError && <p className="hint">Carregando projeto…</p> :
        <Projects projects={projects} onNew={() => setModal({type: 'new'})} onImport={() => setModal({type: 'import'})}/>)}
      {nav.path === 'instances' && <Instances items={instances} onNew={() => setModal({type: 'instance'})} run={run} busy={busy}/>}
      {nav.path === 'logs' && <ActivityView logs={logs} projects={projects}/>}
    </main></div>
    {notice && <div className="toast" role="status"><CircleCheck size={19}/><span>{notice}</span><button className="icon-button" aria-label="Fechar notificação" onClick={() => setNotice('')}><X size={17}/></button></div>}
    {modal?.type === 'instance' && <InstanceForm close={close} done={() => {refresh(); setNotice('Instância cadastrada.');}}/>}
    {modal?.type === 'import' && <ImportForm instances={instances} close={close} done={projectSaved}/>}
    {(modal?.type === 'new' || (modal?.type === 'edit' && detail)) &&
      <ProjectForm project={modal.type === 'edit' ? detail ?? undefined : undefined} instances={instances} close={close} done={projectSaved}/>}
    {detail && (modal?.type === 'new-scene' || modal?.type === 'edit-scene') && <SceneForm project={detail} scene={scene} close={close} done={refresh}/>}
    {detail && modal?.type === 'delete' && <Confirmation title="Remover projeto?" description="O projeto e seu histórico sairão do painel. Os arquivos permanecerão na pasta local." label="Remover projeto" close={close}
      confirm={async () => {await confirm(base, 'DELETE'); window.location.hash = 'projects';}}/>}
    {scene && modal?.type === 'delete-scene' && <Confirmation title="Remover cena?" description={`A cena “${scene.title}” será removida da sequência.`} label="Remover cena" close={close}
      confirm={() => confirm(scenePath, 'DELETE')}/>}
    {scene && modal?.type === 'retry' && <Confirmation title="Solicitar nova tentativa?" description="A tentativa anterior será preservada. Retome o projeto para processar a solicitação."
      label="Solicitar tentativa" close={close} confirm={() => confirm(`${scenePath}/retry`, 'POST')}/>}
    {scene && modal?.type === 'reconcile' && <Confirmation title="Encerrar tentativa incerta?" description="Confirme que você verificou o resultado no provedor. Uma nova tentativa, se desejada, deverá ser solicitada separadamente."
      label="Encerrar tentativa" close={close} confirm={() => confirm(`${scenePath}/reconcile`, 'POST', {acknowledge: true})}/>}
  </div>;
}
