import copy
from fiona import collection
from shapely.geometry import mapping, shape
from shapely import ops
# import numpy as np

# Path
# linkShapeFile = "C:\ICP\qgis\projects\minato-ku\minato-link.shp"
linkShapeFile = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/minato-ku/minato-link.shp"
# nodeShapeFile = "C:\ICP\qgis\projects\minato-ku\minato-node.shp"
nodeShapeFile = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/minato-ku/minato-node.shp"

# new objectid 30,000,000からスタート
newobjectid = 30000000

fromNodes = {}
toNodes = {}

# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count', 'ts_drm_tri', 'legal_spee', 'legal_sp_1')


def check_attributes(f, t, attributes):

    for attr in attributes:
        if f['properties'][attr] != t['properties'][attr]:
            return False
        else:
            return True


def merge_links(a, b, node):
    # 新しいobjectid
    newobjectid = newobjectid + 1

    # TODO 向きを考慮して、方向性のある属性を正しくマージする
    # # from toの両端のnodeidを格納
    # aNodes = (a['properties']['fromnodeid'], a['properties']['tonodeid'])
    # bNodes = (b['properties']['fromnodeid'], b['properties']['tonodeid'])
    #
    # # ノードの位置を特定
    # aNodePos = aNodes.index(node)
    # bNodePos = bNodes.index(node)
    #
    # # 両リンクの向きを確認
    # # <-a- n -b->
    # if aNodePos == 0 and bNodePos = 0:
    # # -a-> n -b->
    # elif aNodePos == 1 and bNodePos = 0:
    # # <-a- n <-b-
    # elif aNodePos == 0 and bNodePos = 1:
    # # -a-> n <-b-
    # elif aNodePos == 1 and bNodePos = 1:

    # TODO deepcopyで新しいレコードを作成する
    newf = copy.deepcopy(f)
    # shape
    tc = t['geometry']['coordinates']
    newf['geometry']['coordinates'].append(t['geometry']['coordinates'])
    newf['objectid'] = newobjectid
    return newf

# リンクレイヤからfromnodeid, tonodeid を取得し、featureをList[objectid] 形式でリスト化　
with collection(linkShapeFile, "r") as fl:
    for feature in fl:
        fromNodeId = feature['properties']['fromnodeid']
        fromNodes[fromNodeId] = {'properties': feature['properties'], 'geometry': feature['geometry']}
        toNodeId = feature['properties']['tonodeid']
        toNodes[toNodeId] = {'properties': feature['properties'], 'geometry': feature['geometry']}

# connlink=2のノードに接続しているリンクを接合する
with collection(nodeShapeFile, "r") as fn:
    for feature in fn:
        connlink = feature['properties']['connlink']
        if connlink == 2:
            nodeId = feature['properties']['objectid']
            # 接合対象のリンクを特定
            if nodeId in fromNodes.keys():
                fromLink = fromNodes[nodeId]
            if nodeId in toNodes.keys():
                toLink = toNodes[nodeId]
            if check_attributes(fromLink, toLink, checkAttributes):
                newLink = merge_links(fromLink, toLink, nodeId)
                print(f"fromLink:{fromLink}")
                print(f"  toLink:{toLink}")
                print(f" newLink:{newLink}")
                break
