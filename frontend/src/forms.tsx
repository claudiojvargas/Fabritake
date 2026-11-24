import { useState, type FormEvent, type ReactNode } from 'react';
import { Upload } from 'lucide-react';
import { api, providerName, type Detail, type Instance, type ProjectInput, type Provider, type Scene, type SceneInput } from './api';
import { Alert, Modal } from './ui';

function optionalInt(data: FormData, key: string) {
  return data.get(key) ? Number(data.get(key)) : null;
}
const string = (data: FormData, name: string) => String(data.get(name) ?? '');
const references = (data: FormData) => data.getAll('references').map(String);

function ReferenceList({available, selected}: {available: string[]; selected: string[]}) {
  const all = Array.from(new Set([...available, ...selected]));
  return all.length > 0 && <fieldset className="reference-options"><legend>Referências</legend>
    {all.map(ref => <label className="check" key={ref}><input type="checkbox" name="references" value={ref} defaultChecked={selected.includes(ref)}/>
      {ref.split('/').at(-1)}{!available.includes(ref) && ' (arquivo ausente)'}</label>)}</fieldset>;
}

function Editor({title, description, close, submit, children, label = 'Salvar'}: {
  title: string; description?: string; close: () => void; submit: (data: FormData) => Promise<void>; children: ReactNode; label?: string;
}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setBusy(true);
    try { await submit(new FormData(event.currentTarget)); close(); }
    catch (error) { setError(String((error as Error).message)); }
    finally { setBusy(false); }
  }
  return <Modal title={title} description={description} close={() => {if (!busy) close();}}>
    <form onSubmit={save} className="editor">
      {error && <Alert>{error}</Alert>}
      <fieldset disabled={busy} className="fields">{children}</fieldset>
      <div className="modal-actions"><button type="button" className="button secondary" onClick={close} disabled={busy}>Cancelar</button>
      <button className="button primary" disabled={busy}>{busy ? 'Salvando…' : label}</button></div>
    </form>
  </Modal>;
}

export function InstanceForm({close, done}: {close: () => void; done: (instance: Instance) => void}) {
  return <Editor title="Nova instância" description="Cada instância do Google Flow usa um perfil de navegador exclusivo." close={close}
    submit={async data => done(await api('/instances', 'POST', {name: string(data, 'name'), provider: string(data, 'provider')}))}>
    <label>Nome<input name="name" required maxLength={120} placeholder="Ex. Simulador local" autoFocus/></label>
    <label>Provedor<select name="provider"><option value="simulated">Simulado</option><option value="flow">Google Flow · diagnóstico</option></select></label>
  </Editor>;
}

export function ProjectForm({project, instances, close, done}: {project?: Detail; instances: Instance[]; close: () => void; done: (project: Detail) => void}) {
  const [instanceId, setInstanceId] = useState(project?.instance_id ?? instances[0]?.id ?? '');
  const mode = instances.find(instance => instance.id === instanceId)?.provider ?? 'simulated';
  return <Editor title={project ? 'Editar projeto' : 'Novo projeto'} close={close} label={project ? 'Salvar projeto' : 'Criar projeto'}
    submit={async data => {
      let id = instanceId;
      if (!id) {
        const instance = await api<Instance>('/instances', 'POST', {name: 'Simulador local', provider: 'simulated'});
        id = instance.id;
        setInstanceId(id);
      }
      const payload: ProjectInput = {
        title: string(data, 'title'), description: string(data, 'description'), ratio: string(data, 'ratio'),
        language: string(data, 'language'), duration: optionalInt(data, 'duration'), provider: mode, instance_id: id,
        references: references(data), settings: {manual_review: !!data.get('review'), model: string(data, 'model') || null,
          timeout: Number(data.get('timeout')), paid_authorized: data.get('paid') === 'on'},
      };
      done(await api(project ? `/projects/${project.id}` : '/projects', project ? 'PUT' : 'POST', payload));
    }}>
    <label>Título<input autoFocus name="title" required maxLength={120} defaultValue={project?.title} placeholder="Nome do projeto"/></label>
    <label>Descrição<textarea name="description" rows={3} defaultValue={project?.description} placeholder="Contexto do projeto"/></label>
    <label>Instância vinculada<select value={instanceId} onChange={event => setInstanceId(event.target.value)}>
      {!instances.length && <option value="">Criar simulador local</option>}
      {instances.map(instance => <option key={instance.id} value={instance.id}>{instance.name} · {providerName(instance.provider)}</option>)}
    </select></label>
    <div className="form-row thirds">
      <label>Proporção<select name="ratio" defaultValue={project?.ratio ?? '16:9'}><option>16:9</option><option>9:16</option><option>1:1</option></select></label>
      <label>Idioma<input name="language" required defaultValue={project?.language ?? 'pt-BR'}/></label>
      <label>Duração alvo (s)<input type="number" name="duration" min="1" max="86400" defaultValue={project?.duration ?? ''}/></label>
    </div>
    <div className="form-row">
      <label>Modelo preferido<input name="model" maxLength={120} defaultValue={project?.settings.model ?? ''} placeholder={mode === 'flow' ? 'Ex. Omni 1.1, se disponível' : 'Opcional'}/></label>
      <label>Tempo limite (s)<input type="number" name="timeout" min="10" max="3600" required defaultValue={project?.settings.timeout ?? 300}/></label>
    </div>
    <label className="check"><input type="checkbox" name="review" defaultChecked={project?.settings.manual_review}/> Exigir aprovação manual de cada cena</label>
    {mode === 'flow' && <p className="hint">O Flow está disponível para diagnóstico. A geração real ainda precisa ser validada.</p>}
    <ReferenceList available={project?.references_available ?? []} selected={project?.references ?? []}/>
  </Editor>;
}

export function SceneForm({project, scene, close, done}: {project: Detail; scene?: Scene; close: () => void; done: () => void}) {
  return <Editor title={scene ? 'Editar cena' : 'Nova cena'} close={close}
    submit={async data => {
      const payload: SceneInput = {title: string(data, 'title'), order: Number(data.get('order')),
        duration: optionalInt(data, 'duration'), prompt: string(data, 'prompt'),
        continuity: string(data, 'continuity') as SceneInput['continuity'], references: references(data)};
      await api(`/projects/${project.id}/scenes${scene ? '/' + scene.id : ''}`, scene ? 'PUT' : 'POST', payload);
      done();
    }}>
    <label>Título<input autoFocus name="title" required maxLength={120} defaultValue={scene?.title} readOnly={!!scene?.attempts.length}/></label>
    <div className="form-row">
      <label>Ordem<input name="order" type="number" min="1" max="9999" required readOnly={!!scene && project.scenes.some(item => item.attempts.length > 0)}
        defaultValue={scene?.order ?? Math.max(0, ...project.scenes.map(item => item.order)) + 1}/></label>
      <label>Duração (s)<input name="duration" type="number" min="1" max="86400" defaultValue={scene?.duration ?? ''}/></label>
    </div>
    <label>Prompt<textarea name="prompt" rows={6} required maxLength={16000} defaultValue={scene?.prompt} placeholder="Descreva a cena, a câmera e o plano final."/></label>
    <label>Continuidade<select name="continuity" defaultValue={scene?.continuity ?? 'previous_final_frame'}>
      <option value="previous_final_frame">Usar frame final da cena anterior</option><option value="explicit_reference">Usar referência específica</option><option value="none">Sem continuidade</option>
    </select></label>
    <ReferenceList available={project.references_available} selected={scene?.references ?? []}/>
  </Editor>;
}

export function ImportForm({instances, close, done}: {instances: Instance[]; close: () => void; done: (project: Detail) => void}) {
  return <Editor title="Importar projeto" description="Selecione um manifesto JSON ou um roteiro Markdown no formato Fabritake v1." close={close} label="Importar"
    submit={async data => {
      const file = data.get('upload') as File;
      let instanceId = string(data, 'instance');
      const content = await file.text();
      const markdown = file.name.toLowerCase().endsWith('.md');
      const manifest: unknown = markdown ? undefined : JSON.parse(content);
      if (!instanceId) instanceId = (await api<Instance>('/instances', 'POST', {name: 'Simulador local', provider: 'simulated'})).id;
      done(await api(markdown ? '/projects/import-markdown' : '/projects/import', 'POST', {
        instance_id: instanceId, ...(markdown ? {markdown: content} : {manifest}),
      }));
    }}>
    <label className="upload-label"><Upload size={18}/> Arquivo do projeto<input type="file" name="upload" accept=".json,.md" required/></label>
    <label>Instância vinculada<select name="instance">{!instances.length && <option value="">Criar simulador local</option>}
      {instances.map(instance => <option key={instance.id} value={instance.id}>{instance.name} · {providerName(instance.provider as Provider)}</option>)}
    </select></label>
  </Editor>;
}

export function Confirmation({title, description, label, close, confirm}: {
  title: string; description: string; label: string; close: () => void; confirm: () => Promise<void>
}) {
  return <Editor title={title} description={description} label={label} close={close} submit={confirm}><span/></Editor>;
}
