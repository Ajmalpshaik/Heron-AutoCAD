using System;
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
            // Publishing opens the sheets itself: no lock, no transaction around it.
            if (request.Operation == "publish_pdf") return Outside(request, doc);
            try
            {
                using (var args = RunArgs.Parse(request.Args))
                using (doc.LockDocument())
                using (var tr = doc.Database.TransactionManager.StartTransaction())
                {
                    var result = Dispatch(request.Operation, doc.Database, tr, args);
                    // A read leaves nothing behind, not even an empty undo step.
                    if (level == Risk.Read) tr.Abort();
                    else tr.Commit();
                    return result;
                }
            }
            catch (RunRefusal refusal)
            {
                return RunResult.Failed(refusal.Message + " " + Texts.NothingChanged);
            }
            catch (AcException ex)
            {
                HeronLog.Error("Operation " + request.Operation, ex);
                if (ex.ErrorStatus == ErrorStatus.OnLockedLayer)
                    return RunResult.Failed("An object this needs is on a locked layer. Unlock the layer first. " + Texts.NothingChanged);
                return RunResult.Failed("AutoCAD refused it (" + ex.ErrorStatus + "). " + Texts.NothingChanged);
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Operation " + request.Operation, ex);
                return RunResult.Failed("Heron in AutoCAD hit an error: " + ex.Message + " " + Texts.NothingChanged);
            }
        }

        /// <summary>An operation that must not run inside a lock and a transaction; it changes nothing in the drawing.</summary>
        private static RunResult Outside(RunRequest request, Document doc)
        {
            try
            {
                using (var args = RunArgs.Parse(request.Args))
                    return PublishPdf.Run(doc, args);
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

        private static RunResult Dispatch(string operation, Database db, Transaction tr, RunArgs args)
        {
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
