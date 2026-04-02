// Minimal observable store for PDF inline edits
// No external dependencies needed

const store = new Map(); // fileId -> string -> array of edits
const listeners = new Set();
// For undo/redo
const undoStacks = new Map();
const redoStacks = new Map();

const EMPTY_EDITS = []; // Stable reference to prevent infinite loops in React's useSyncExternalStore

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

export const activeFileId = 'default_file'; // Could be dynamic, using a default for simplicity if single file

export const pdfEditStore = {
  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  getEdits(fileId = activeFileId) {
    return store.get(fileId) || EMPTY_EDITS;
  },

  commitEdit(fileId = activeFileId, edit) {
    if (!store.has(fileId)) store.set(fileId, []);
    if (!undoStacks.has(fileId)) undoStacks.set(fileId, []);
    
    const currentEdits = [...this.getEdits(fileId)];
    undoStacks.get(fileId).push(currentEdits);
    
    // Clear redo stack on new action
    if (!redoStacks.has(fileId)) redoStacks.set(fileId, []);
    redoStacks.get(fileId).length = 0;

    // Prune undo stack to 50 items memory limit
    if (undoStacks.get(fileId).length > 50) {
      undoStacks.get(fileId).shift();
    }

    store.get(fileId).push(edit);
    emit();
  },

  updateEdit(fileId = activeFileId, pageNum, nodeIndex, partialEdit) {
    if (!store.has(fileId)) return;
    
    // Save state for undo/redo
    if (!undoStacks.has(fileId)) undoStacks.set(fileId, []);
    const currentEdits = [...this.getEdits(fileId)];
    undoStacks.get(fileId).push(currentEdits.map(e => ({...e}))); // Deep copy the array of objects
    
    if (!redoStacks.has(fileId)) redoStacks.set(fileId, []);
    redoStacks.get(fileId).length = 0;

    if (undoStacks.get(fileId).length > 50) {
      undoStacks.get(fileId).shift();
    }

    const edits = store.get(fileId);
    const targetIdx = edits.findIndex(e => e.pageNum === pageNum && e.nodeIndex === nodeIndex);
    if (targetIdx !== -1) {
      edits[targetIdx] = { ...edits[targetIdx], ...partialEdit };
      emit();
    }
  },

  undo(fileId = activeFileId) {
    if (!undoStacks.has(fileId) || undoStacks.get(fileId).length === 0) return;
    
    if (!redoStacks.has(fileId)) redoStacks.set(fileId, []);
    const currentEdits = [...this.getEdits(fileId)];
    redoStacks.get(fileId).push(currentEdits);

    const previousEdits = undoStacks.get(fileId).pop();
    store.set(fileId, previousEdits);
    emit();
  },

  redo(fileId = activeFileId) {
    if (!redoStacks.has(fileId) || redoStacks.get(fileId).length === 0) return;
    
    if (!undoStacks.has(fileId)) undoStacks.set(fileId, []);
    const currentEdits = [...this.getEdits(fileId)];
    undoStacks.get(fileId).push(currentEdits);

    const nextEdits = redoStacks.get(fileId).pop();
    store.set(fileId, nextEdits);
    emit();
  },

  clear(fileId = activeFileId) {
    store.delete(fileId);
    undoStacks.delete(fileId);
    redoStacks.delete(fileId);
    emit();
  }
};
