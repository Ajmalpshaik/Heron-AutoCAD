using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The plug-in's own operations, for what COM has no call for (D-40). Main
    /// thread only (AcadJobHost queues it through IdleQueue).
    ///
    /// Each one runs under a document lock in one transaction: it all lands, or
    /// none of it does. A refusal or an AutoCAD error aborts the transaction,
    /// which is why every failure can end "Nothing was changed."
    /// </summary>
    internal static class PluginRunner
    {
        public static RunResult Run(RunRequest request)
        {
            var doc = AcApp.DocumentManager.MdiActiveDocument;
            if (doc == null) return RunResult.Failed("No drawing is open in AutoCAD. " + Texts.NothingChanged);
            if (!DrawingNames.Same(doc.Name, request.Drawing)) return RunResult.Failed(Texts.WrongDrawing(doc.Name, request.Drawing));
            PluginOperations.TryLevel(request.Operation, out var level);
            HeronLog.Write("operation " + request.Operation + " on " + doc.Name);
            // Publishing opens the sheets itself, and showing only selects and
            // zooms: no lock, no transaction around either.
            if (request.Operation == "publish_pdf" || request.Operation == "show") return Outside(request, doc);
            try
            {
                using (var args = RunArgs.Parse(request.Args))
                using (doc.LockDocument())
                {
                    // The sun hangs off the model viewport's record, which AutoCAD
                    // does not keep up to date as the view moves: write the live
                    // view into it first, and give the screen the new sun after.
                    var viewports = request.Operation == "set_sun";
                    if (viewports) doc.Editor.UpdateTiledViewportsInDatabase();
                    RunResult result;
                    _afterCommit = null;
                    _afterAbort = null;
                    var committed = false;
                    try
                    {
                        using (var tr = doc.Database.TransactionManager.StartTransaction())
                        {
                            result = Dispatch(request.Operation, doc, tr, args);
                            // A read leaves nothing behind, not even an empty undo step.
                            if (level == Risk.Read) tr.Abort();
                            else
                            {
                                tr.Commit();
                                committed = true;
                            }
                        }
                    }
                    catch
                    {
                        // The transaction is aborted and closed: now what it could not take back.
                        _afterCommit = null;
                        RunAfter(ref _afterAbort);
                        throw;
                    }
                    _afterAbort = null;
                    if (viewports) doc.Editor.UpdateTiledViewportsFromDatabase();
                    if (committed) RunAfter(ref _afterCommit);
                    else _afterCommit = null;
                    return result;
                }
            }
            catch (RunRefusal refusal)
            {
                _afterCommit = null;
                _afterAbort = null;
                return RunResult.Failed(refusal.Message + " " + Texts.NothingChanged);
            }
            catch (AcException ex)
            {
                _afterCommit = null;
                _afterAbort = null;
                HeronLog.Error("Operation " + request.Operation, ex);
                if (ex.ErrorStatus == ErrorStatus.OnLockedLayer)
                    return RunResult.Failed("An object this needs is on a locked layer. Unlock the layer first. " + Texts.NothingChanged);
                return RunResult.Failed("AutoCAD refused it (" + ex.ErrorStatus + "). " + Texts.NothingChanged);
            }
            catch (System.Exception ex)
            {
                _afterCommit = null;
                _afterAbort = null;
                HeronLog.Error("Operation " + request.Operation, ex);
                return RunResult.Failed("Heron in AutoCAD hit an error: " + ex.Message + " " + Texts.NothingChanged);
            }
        }

        // What an operation leaves for after its transaction (main thread only): a new
        // sheet put on screen or a regen once it is committed, a half-made layout
        // deleted once it is aborted (AutoCAD's layout manager is not undone by the abort).
        private static List<Action>? _afterCommit;
        private static List<Action>? _afterAbort;

        /// <summary>Do this once the operation's transaction is committed; never when it is aborted.</summary>
        public static void AfterCommit(Action action) => (_afterCommit ??= new List<Action>()).Add(action);

        /// <summary>Do this, still under the document lock, if the operation fails and its transaction is aborted.</summary>
        public static void AfterAbort(Action action) => (_afterAbort ??= new List<Action>()).Add(action);

        private static void RunAfter(ref List<Action>? list)
        {
            var pending = list;
            list = null;
            if (pending == null) return;
            foreach (var action in pending)
            {
                try
                {
                    action();
                }
                catch (System.Exception ex)
                {
                    // The operation itself has landed: a failed switch or regen is logged, not reported as a failure.
                    HeronLog.Error("After the operation", ex);
                }
            }
        }

        /// <summary>An operation that must not run inside a lock and a transaction; it changes nothing in the drawing.</summary>
        private static RunResult Outside(RunRequest request, Document doc)
        {
            try
            {
                using (var args = RunArgs.Parse(request.Args))
                    return request.Operation == "show" ? Showing.Show(doc, args) : PublishPdf.Run(doc, args);
            }
            catch (RunRefusal refusal)
            {
                return RunResult.Failed(refusal.Message);
            }
            catch (AcException ex)
            {
                HeronLog.Error("Operation " + request.Operation, ex);
                return RunResult.Failed("AutoCAD refused it (" + ex.ErrorStatus + "). The drawing was not changed.");
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Operation " + request.Operation, ex);
                return RunResult.Failed("Heron in AutoCAD hit an error: " + ex.Message + " The drawing was not changed.");
            }
        }

        private static RunResult Dispatch(string operation, Document doc, Transaction tr, RunArgs args)
        {
            var db = doc.Database;
            switch (operation)
            {
                case "solid_topology": return SolidOperations.Topology(db, tr, args);
                case "loft": return SolidOperations.Loft(db, tr, args);
                case "fillet_edges": return SolidOperations.Fillet(db, tr, args);
                case "chamfer_edges": return SolidOperations.Chamfer(db, tr, args);
                case "shell": return SolidOperations.Shell(db, tr, args);
                case "press_pull": return SolidOperations.PressPull(db, tr, args);
                case "thicken": return SolidOperations.Thicken(db, tr, args);
                case "super_hatch": return SuperHatch.Make(db, tr, args);
                case "add_light": return RenderSetup.AddLight(db, tr, args);
                case "create_material": return RenderSetup.CreateMaterial(db, tr, args);
                case "dimension_lines": return DimensionLines.Read(db, tr, args);
                case "move_dimension_lines": return DimensionLines.Move(db, tr, args);
                case "annotation_scales": return AnnotationScales.Read(db, tr, args);
                case "set_annotation_scales": return AnnotationScales.Set(db, tr, args);
                case "layer_state_names": return LayerStates.Names(db, tr, args);
                case "layer_state": return LayerStates.Change(db, tr, args);
                case "current_view": return RenderView.CurrentView(doc, tr);
                case "list_lights": return RenderView.ListLights(doc, tr);
                case "switch_lights": return RenderView.SwitchLights(db, tr, args);
                case "set_sun": return RenderView.SetSun(doc, tr, args);
                case "add_camera_view": return RenderView.AddCameraView(doc, tr, args);
                case "sync_attributes": return BlockAttributes.Sync(db, tr, args);
                case "excel_table": return ExcelTables.Make(db, tr, args);
                case "update_table_links": return ExcelTables.Update(db, tr, args);
                case "active_sheet": return Sheets.ActiveSheet(db, tr);
                case "create_layout": return Sheets.CreateLayout(doc, db, tr, args);
                case "add_viewport": return Sheets.AddViewport(doc, db, tr, args);
                default: throw new RunRefusal(Texts.UnknownOperation(operation));
            }
        }
    }

    /// <summary>What every operation needs: objects by handle, and the layer and colour asked for.</summary>
    internal static class RunDrawing
    {
        public static ObjectId IdOf(Database db, string handle)
        {
            long value;
            try
            {
                value = Convert.ToInt64((handle ?? "").Trim(), 16);
            }
            catch (System.Exception ex) when (ex is FormatException || ex is OverflowException || ex is ArgumentException)
            {
                throw new RunRefusal("'" + handle + "' is not a handle.");
            }
            if (!db.TryGetObjectId(new Handle(value), out var id) || id.IsNull || id.IsErased)
                throw new RunRefusal("Nothing in this drawing has the handle " + handle + ". autocad_list_entities gives current handles.");
            return id;
        }

        /// <summary>The object behind a handle, as the type the operation works on, or a refusal naming what it is.</summary>
        public static T Open<T>(Transaction tr, Database db, string handle, OpenMode mode, string wanted) where T : DBObject
        {
            var found = tr.GetObject(IdOf(db, handle), OpenMode.ForRead);
            if (!(found is T typed)) throw new RunRefusal(handle + " is " + Kind(found) + ", not " + wanted + ".");
            if (mode == OpenMode.ForWrite) typed.UpgradeOpen();
            return typed;
        }

        public static string Kind(DBObject obj)
        {
            var name = obj.GetRXClass().DxfName;
            return "a " + (string.IsNullOrEmpty(name) ? obj.GetType().Name : name.ToLowerInvariant());
        }

        /// <summary>
        /// The layer (made if missing, like every Heron tool) and colour asked
        /// for, on something new. The rest comes from the drawing's current
        /// settings, as AutoCAD's own commands do.
        /// </summary>
        public static void Style(Entity entity, Database db, Transaction tr, RunArgs args, Utf8JsonWriter? notes = null)
        {
            var layer = args.Text("layer").Trim();
            if (layer.Length > 0)
            {
                var layers = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                if (!layers.Has(layer))
                {
                    try
                    {
                        SymbolUtilityServices.ValidateSymbolName(layer, false);
                    }
                    catch (AcException)
                    {
                        throw new RunRefusal("'" + layer + "' cannot be a layer name.");
                    }
                    layers.UpgradeOpen();
                    var record = new LayerTableRecord { Name = layer };
                    layers.Add(record);
                    tr.AddNewlyCreatedDBObject(record, true);
                    notes?.WriteString("layer_created", layer);
                }
                entity.Layer = layer;
            }
            if (args.Has("color")) entity.ColorIndex = (int)args.Number("color");
        }

        public static void WritePoint(Utf8JsonWriter w, string name, double x, double y, double z)
        {
            w.WriteStartArray(name);
            w.WriteNumberValue(Math.Round(x, 9));
            w.WriteNumberValue(Math.Round(y, 9));
            w.WriteNumberValue(Math.Round(z, 9));
            w.WriteEndArray();
        }

        public static void WriteNumbers(Utf8JsonWriter w, string name, int[] values)
        {
            w.WriteStartArray(name);
            foreach (var value in values) w.WriteNumberValue(value);
            w.WriteEndArray();
        }
    }
}
