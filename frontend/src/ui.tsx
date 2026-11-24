import { useEffect, useRef, type ReactNode } from 'react';
import { CircleAlert, Clapperboard, X } from 'lucide-react';
import { states } from './api';

export function Logo({ small = false }: {small?: boolean}) {
  return <span className={small ? 'brand-symbol small' : 'brand-symbol'} aria-hidden="true"><i/><i/></span>;
}

export function Badge({state}: {state: string}) {
  const style = ['completed','available'].includes(state) ? 'green' :
    ['running','queued','generating','preparing','diagnostic','simulated'].includes(state) ? 'purple' :
    ['failed','blocked','requires_reconciliation'].includes(state) ? 'red' :
    ['paused','pausing','awaiting_review','manual_login','stale'].includes(state) ? 'amber' : 'gray';
  return <span className={`badge ${style}`}><i/>{states[state] ?? state}</span>;
}

export function Progress({done, total}: {done: number; total: number}) {
  const percent = total ? Math.round(100 * done / total) : 0;
  return <div className="progress" role="progressbar" aria-label="Cenas concluídas" aria-valuenow={percent}>
    <span style={{width: `${percent}%`}}/>
  </div>;
}

export function Empty({title, children, action}: {title: string; children?: ReactNode; action?: ReactNode}) {
  return <div className="empty"><span className="empty-icon"><Clapperboard size={23}/></span><strong>{title}</strong>
    {children && <p>{children}</p>}{action}</div>;
}

export function Alert({children}: {children: ReactNode}) {
  return <div className="alert" role="alert"><CircleAlert size={17}/><span>{children}</span></div>;
}

export function Modal({title, description, close, children}: {title: string; description?: string; close: () => void; children: ReactNode}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={ref} onCancel={event => {event.preventDefault(); close();}} className="modal" aria-labelledby="dialog-title">
    <div className="modal-head"><div><h2 id="dialog-title">{title}</h2>{description && <p>{description}</p>}</div>
    <button className="icon-button" aria-label="Fechar" onClick={close}><X size={19}/></button></div>
    {children}
  </dialog>;
}
