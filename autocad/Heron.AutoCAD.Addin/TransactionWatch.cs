using System;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Watches one plug-in operation's transaction for anything that could be a
    /// change (D-140, issue #80): every object opened for change, added,
    /// modified, erased, taken out or put back in the drawing, and every
    /// variable changed. OperationTransaction decides from that whether to
    /// commit; an operation that touched nothing is aborted, so it leaves no
    /// empty undo step. Main thread only; hooked for the operation alone.
    /// </summary>
    internal sealed class TransactionWatch : IDisposable
    {
        private readonly Database _db;
        private readonly OperationTransaction _end;
        private bool _hooked;

        public TransactionWatch(Database db, OperationTransaction end)
        {
            _db = db;
            _end = end;
            _db.ObjectOpenedForModify += OnObject;
            _db.ObjectAppended += OnObject;
            _db.ObjectModified += OnObject;
            _db.ObjectErased += OnErased;
            _db.ObjectUnappended += OnObject;
            _db.ObjectReappended += OnObject;
            _db.SystemVariableChanged += OnHeaderVariable;
            AcApp.SystemVariableChanged += OnVariable;
            _hooked = true;
        }

        private void OnObject(object? sender, ObjectEventArgs e) => _end.Object();

        private void OnErased(object? sender, ObjectErasedEventArgs e) => _end.Object();

        private void OnHeaderVariable(object? sender, Autodesk.AutoCAD.DatabaseServices.SystemVariableChangedEventArgs e) => _end.Variable();

        private void OnVariable(object? sender, Autodesk.AutoCAD.ApplicationServices.SystemVariableChangedEventArgs e) => _end.Variable();

        public void Dispose()
        {
            if (!_hooked) return;
            _hooked = false;
            try
            {
                _db.ObjectOpenedForModify -= OnObject;
                _db.ObjectAppended -= OnObject;
                _db.ObjectModified -= OnObject;
                _db.ObjectErased -= OnErased;
                _db.ObjectUnappended -= OnObject;
                _db.ObjectReappended -= OnObject;
                _db.SystemVariableChanged -= OnHeaderVariable;
                AcApp.SystemVariableChanged -= OnVariable;
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Stop watching the operation's transaction", ex);
            }
        }
    }
}
