using System;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// How a plug-in operation's transaction ends (D-140, issue #80).
    ///
    /// Each operation runs in one transaction. A read is always aborted, so it
    /// leaves nothing behind, not even an empty undo step (D-34). Any other
    /// operation is committed only when it really touched the drawing: an
    /// object opened for change, added, erased, taken out or put back, a
    /// drawing variable changed, or work left for after the commit. An
    /// operation that did none of those is aborted like a read: with nothing
    /// written, aborting and committing leave the same drawing, and the abort
    /// cannot leave an empty step in the undo list (Heron for Revit's D-160).
    ///
    /// The add-in feeds AutoCAD's own database events in; the rule lives here so
    /// it is tested offline. Main thread only, like the operation itself.
    /// </summary>
    public sealed class OperationTransaction
    {
        private readonly Risk _level;
        private int _objects;
        private int _variables;

        public OperationTransaction(Risk level) => _level = level;

        /// <summary>An object was opened for change, added, modified, erased, taken out or put back.</summary>
        public void Object() => _objects++;

        /// <summary>A drawing (header) or AutoCAD variable changed while the operation ran.</summary>
        public void Variable() => _variables++;

        /// <summary>Nothing in the drawing was touched while the operation ran.</summary>
        public bool Untouched => _objects == 0 && _variables == 0;

        /// <summary>
        /// True: commit. False: abort.
        /// </summary>
        /// <param name="workAfter">The operation left work for after its transaction (a sheet to put on screen, a regen, a clean-up on abort).</param>
        public bool Commit(bool workAfter)
        {
            if (_level == Risk.Read) return false;
            // Anything at all that could be a change keeps today's commit: aborting a
            // real change would lose the modeller's job, an empty step costs one Ctrl+Z.
            return !Untouched || workAfter;
        }
    }

    /// <summary>
    /// An operation failed after part of it landed outside its transaction, so
    /// "Nothing was changed" would be untrue. The message says what is left.
    /// </summary>
    public sealed class RunLeftBehind : Exception
    {
        public RunLeftBehind(string message) : base(message) { }
    }

    /// <summary>
    /// A new object AutoCAD adds to the drawing itself (GeoLocationData.PostToDb),
    /// then handed to the operation's transaction (D-140, issue #258).
    ///
    /// Either it ends up inside the transaction, so it lands or goes with the
    /// rest of the job and the job stays one undo step; or it is taken off again
    /// at once and the operation is refused. It is never left in the drawing
    /// outside the transaction, where an abort would not take it back.
    /// </summary>
    public static class PostedObject
    {
        /// <param name="what">The object, in words: "the geographic location".</param>
        /// <param name="post">Adds it to the drawing. If this throws, nothing was added.</param>
        /// <param name="adopt">Hands it to the transaction (AddNewlyCreatedDBObject).</param>
        /// <param name="takeBack">Takes it out of the drawing again (EraseFromDb).</param>
        /// <param name="log">Logs an error that is not the answer.</param>
        public static void Post(string what, Action post, Action adopt, Action takeBack, Action<string, Exception> log)
        {
            post();
            try
            {
                adopt();
            }
            catch (Exception ex)
            {
                log("Handing " + what + " to the transaction", ex);
                try
                {
                    takeBack();
                }
                catch (Exception inner)
                {
                    log("Taking " + what + " back off", inner);
                    throw new RunLeftBehind(Texts.PostedLeftBehind(what));
                }
                throw new RunRefusal(Texts.PostedTakenBack(what));
            }
        }
    }
}
