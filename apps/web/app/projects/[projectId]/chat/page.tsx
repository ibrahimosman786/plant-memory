"use client";

import { FormEvent, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, BookOpen, Check, Loader2, MessageSquare, RotateCcw, Sparkles } from "lucide-react";
import { api, type ChatAnswer } from "@/lib/api";
import { useEvidence } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Select, TextArea } from "@/components/ui/input";

type Turn = { question: string; answer: ChatAnswer };
const suggestions = ["What do the records say about CP-101?", "Find conflicting instrument ranges.", "What evidence is missing for a panel replacement?"];

export default function ChatPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const snapshots = useQuery({ queryKey: ["snapshots", projectId], queryFn: () => api.snapshots(projectId) });
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.status });
  const [selected, setSelected] = useState("");
  const snapshot = selected || snapshots.data?.[0]?.id || "";
  return <div className="mx-auto max-w-5xl space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-caption uppercase tracking-[0.15em] text-primary">Your project assistant</p><h1 className="text-display font-semibold">Ask Plant Memory</h1><p className="mt-3 text-body text-muted">Answers from your records, with the evidence one click away.</p></div><div className="w-full sm:w-64"><label htmlFor="chat-snapshot" className="mb-2 block text-caption text-muted">Document snapshot</label><Select id="chat-snapshot" value={snapshot} onChange={e => setSelected(e.target.value)}><option value="" disabled>Select records</option>{snapshots.data?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></div></header>
    {snapshots.isLoading ? <p role="status">Loading project records…</p> : snapshots.error ? <p role="alert">{snapshots.error.message}</p> : snapshot ? <Conversation key={`${projectId}:${snapshot}`} projectId={projectId} snapshot={snapshot} models={status.data?.models ?? []} defaultModel={status.data?.default_model ?? ""} configured={Boolean(status.data?.model_configured)} /> : <div className="rounded-xl border border-hairline bg-white p-8"><h2 className="text-heading">Add records to start a conversation</h2><p className="my-3 text-body text-muted">Upload your documents, wait for processing, then create a snapshot.</p><Link className="text-primary underline" href={`/projects/${projectId}/documents`}>Open documents</Link></div>}
  </div>;
}

function Conversation({projectId, snapshot, models, defaultModel, configured}: {projectId: string; snapshot: string; models: string[]; defaultModel: string; configured: boolean}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [model, setModel] = useState("");
  const evidence = useEvidence();
  const end = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: (text: string) => api.chat(projectId, {question: text, snapshot_id: snapshot, model: model || defaultModel,
      history: turns.slice(-6).flatMap(t => [{role: "user" as const, content: t.question}, {role: "assistant" as const, content: [...t.answer.analysis.claims.map(c => c.statement), ...t.answer.analysis.limitations].join("\n").slice(0,6000)}])}),
    onSuccess: (answer, text) => {setTurns(t => [...t, {question: text, answer}]); setQuestion(""); requestAnimationFrame(() => end.current?.scrollIntoView({block: "nearest"}));},
  });
  function submit(e: FormEvent) {e.preventDefault(); if(question.trim().length >= 3 && !ask.isPending) ask.mutate(question.trim());}
  return <section className="overflow-hidden rounded-2xl border border-hairline bg-white shadow-sm">
    <div className="flex items-center justify-between gap-3 border-b border-hairline px-5 py-4"><div className="flex items-center gap-2 text-ui text-primary"><Sparkles size={17}/><span>Grounded in this snapshot</span></div><Button variant="ghost" disabled={ask.isPending || !turns.length} onClick={() => {setTurns([]);ask.reset();}}><RotateCcw size={14}/>New chat</Button></div>
    <div className="max-h-[58dvh] min-h-80 overflow-y-auto px-5 py-8 sm:px-8" role="log" aria-label="Conversation" aria-live="polite">
      {!turns.length && !ask.isPending ? <div className="mx-auto max-w-xl py-5 text-center"><div className="mx-auto mb-5 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary"><MessageSquare size={26}/></div><h2 className="text-2xl font-semibold">What would you like to understand?</h2><p className="mb-7 mt-3 text-body text-muted">Ask about equipment, compare records, or explore the impact of a proposed change.</p><div className="space-y-2 text-left">{suggestions.map(text => <button key={text} onClick={() => setQuestion(text)} className="flex w-full items-center justify-between gap-3 rounded-xl border border-hairline px-4 py-3 text-ui hover:bg-canvas">{text}<ArrowUp size={15} className="rotate-45 text-primary"/></button>)}</div></div> : null}
      {turns.map((turn,i) => <article key={i} className="mb-8 space-y-5"><div className="ml-auto max-w-[90%] rounded-2xl rounded-tr-sm bg-primary px-5 py-3 text-body text-white whitespace-pre-wrap">{turn.question}</div><div className="space-y-4"><p className="flex items-center gap-2 text-ui font-semibold text-primary"><Sparkles size={16}/>Plant Memory</p>{turn.answer.analysis.claims.map((claim,j) => <div key={j}><p className="text-body whitespace-pre-wrap">{claim.statement}</p><div className="mt-2 flex flex-wrap gap-2">{claim.evidence_ids.map(id => <button key={id} onClick={() => evidence.open([id])} className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-canvas px-2 py-1 text-caption text-primary hover:bg-primary/10"><BookOpen size={12}/>{turn.answer.sources.find(s => s.id === id)?.filename ?? "View source"}</button>)}</div></div>)}{turn.answer.analysis.questions_for_engineer.map((q,j) => <p key={j} className="border-l-2 border-primary/30 pl-3 text-body">{q}</p>)}{turn.answer.analysis.limitations.length ? <div className="rounded-lg bg-canvas p-3 text-caption leading-relaxed text-muted">{turn.answer.analysis.limitations.map((l,j) => <p key={j}>{l}</p>)}</div> : null}<details className="text-caption text-muted"><summary className="cursor-pointer">How this answer was prepared · {turn.answer.model.split('/')[1]}</summary><ul className="mt-2 space-y-1">{turn.answer.steps.map(step => <li key={step} className="flex items-center gap-2"><Check size={12}/>{step}</li>)}</ul></details></div></article>)}
      {ask.isPending ? <div role="status" className="space-y-4"><p className="ml-auto max-w-[90%] rounded-2xl bg-primary px-5 py-3 text-white text-body">{ask.variables}</p><p className="flex items-center gap-2 text-body text-muted"><Loader2 className="animate-spin" size={17}/>Searching records and preparing your answer…</p></div> : null}
      <div ref={end}/>
    </div>
    <form onSubmit={submit} className="border-t border-hairline bg-canvas/60 p-4 sm:p-5">
      {ask.error ? <div role="alert" className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-body text-amber-950"><p>{ask.error.message}</p><p className="mt-1 text-caption">Your question is preserved. Retry after resolving the connection issue.</p></div> : null}
      <label htmlFor="chat-question" className="sr-only">Ask a question about your project</label><TextArea id="chat-question" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask about your project records…" className="min-h-24 resize-none bg-white" minLength={3} maxLength={2000} required disabled={ask.isPending}/>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><Select aria-label="AI model" value={model || defaultModel} onChange={e => setModel(e.target.value)} disabled={ask.isPending} className="w-auto max-w-full border-transparent bg-transparent text-caption">{models.map(id => <option key={id} value={id}>{id.split('/')[1]}</option>)}</Select><Button type="submit" disabled={ask.isPending || !configured || !defaultModel || question.trim().length < 3}>Send question <ArrowUp size={16}/></Button></div><p className="mt-3 text-center text-[11px] text-muted">AI answers need engineer review. Chat stays in this page; changing snapshots or leaving clears the conversation.</p>
    </form>
  </section>;
}
