import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DndContext, DragOverlay, PointerSensor, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core';
import { Badge } from '@/components/ui/badge';
import { FileText, MapPin } from 'lucide-react';
import { FitBadge } from '@/pages/CandidatesPage';

const STAGE_DOT = {
  Applied: 'bg-sky-500',
  Screening: 'bg-amber-500',
  Interview: 'bg-violet-500',
  Offer: 'bg-primary',
  Hired: 'bg-green-600',
  Rejected: 'bg-red-500',
};

function CandidateCard({ candidate, dragging }) {
  return (
    <div
      className={`bg-card rounded-lg border border-border p-3 space-y-1.5 ${dragging ? 'shadow-md scale-[1.02]' : 'hover:shadow-sm'} transition-shadow cursor-grab active:cursor-grabbing`}
    >
      <div className="flex items-center gap-1.5">
        <span className="font-medium text-sm truncate flex-1">{candidate.name}</span>
        <span title={candidate.resume_file_id ? 'Resume attached' : 'No resume on file'} className="inline-flex shrink-0">
          <FileText className={`h-3.5 w-3.5 shrink-0 ${candidate.resume_file_id ? 'text-primary' : 'text-muted-foreground/30'}`} data-testid={candidate.resume_file_id ? 'resume-indicator-yes' : 'resume-indicator-no'} />
        </span>
        <FitBadge score={candidate.fit_score} summary={candidate.fit_score_summary} />
      </div>
      {candidate.candidate_code && (
        <div className="text-[10px] font-mono text-muted-foreground/70" data-testid={`kanban-candidate-code-${candidate.id}`}>{candidate.candidate_code}</div>
      )}
      <div className="text-xs text-muted-foreground truncate">{candidate.current_title || '—'}{candidate.current_company ? ` @ ${candidate.current_company}` : ''}</div>
      {candidate.location && (
        <div className="text-xs text-muted-foreground flex items-center gap-1"><MapPin className="h-3 w-3" />{candidate.location}</div>
      )}
      <div className="flex flex-wrap gap-1 pt-0.5">
        {(candidate.tags || []).slice(0, 3).map((t) => (
          <Badge key={t} variant="secondary" className="text-[10px] px-1.5 py-0">{t}</Badge>
        ))}
      </div>
    </div>
  );
}

function DraggableCard({ candidate, canDrag }) {
  const navigate = useNavigate();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: candidate.id, disabled: !canDrag });
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      data-testid={`kanban-candidate-card-${candidate.id}`}
      style={{ opacity: isDragging ? 0.4 : 1 }}
      onClick={() => {
        if (!isDragging) navigate(`/candidates/${candidate.id}`);
      }}
    >
      <CandidateCard candidate={candidate} />
    </div>
  );
}

function StageColumn({ stage, candidates, canDrag }) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  return (
    <div
      ref={setNodeRef}
      data-testid={`kanban-stage-${stage.toLowerCase()}`}
      className={`w-[280px] shrink-0 bg-secondary rounded-xl border border-border flex flex-col max-h-[calc(100vh-260px)] ${isOver ? 'ring-2 ring-primary/60' : ''}`}
    >
      <div className="sticky top-0 px-3 py-2.5 flex items-center gap-2 border-b border-border bg-secondary rounded-t-xl z-10">
        <span className={`h-2 w-2 rounded-full ${STAGE_DOT[stage] || 'bg-muted-foreground'}`} />
        <span className="font-display text-sm font-semibold">{stage}</span>
        <Badge variant="outline" className="ml-auto tabular-nums bg-card">{candidates.length}</Badge>
      </div>
      <div className="p-2.5 space-y-2 overflow-y-auto thin-scroll flex-1">
        {candidates.map((c) => (
          <DraggableCard key={c.id} candidate={c} canDrag={canDrag} />
        ))}
        {candidates.length === 0 && (
          <div className="text-xs text-muted-foreground text-center py-6 border border-dashed border-border rounded-lg">No candidates</div>
        )}
      </div>
    </div>
  );
}

export default function KanbanBoard({ stages, candidates, onMove, canDrag = true }) {
  const [activeId, setActiveId] = useState(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const byStage = useMemo(() => {
    const m = {};
    stages.forEach((s) => (m[s] = []));
    candidates.forEach((c) => {
      if (m[c.stage]) m[c.stage].push(c);
    });
    return m;
  }, [stages, candidates]);

  const activeCandidate = candidates.find((c) => c.id === activeId);

  return (
    <DndContext
      sensors={sensors}
      onDragStart={(e) => setActiveId(e.active.id)}
      onDragEnd={(e) => {
        setActiveId(null);
        const { active, over } = e;
        if (!over) return;
        const cand = candidates.find((c) => c.id === active.id);
        if (cand && cand.stage !== over.id) onMove(cand, over.id);
      }}
      onDragCancel={() => setActiveId(null)}
    >
      <div className="flex gap-4 overflow-x-auto thin-scroll pb-4">
        {stages.map((s) => (
          <StageColumn key={s} stage={s} candidates={byStage[s] || []} canDrag={canDrag} />
        ))}
      </div>
      <DragOverlay>{activeCandidate ? <div className="w-[256px]"><CandidateCard candidate={activeCandidate} dragging /></div> : null}</DragOverlay>
    </DndContext>
  );
}
