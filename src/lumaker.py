import copy
from fiona import collection, open
from shapely.geometry import mapping, shape
from shapely import ops
# import numpy as np

# Path
# linkShapeFile = "C:\ICP\qgis\projects\minato-ku\minato-link.shp"
linkShapeFile = "C:\qgis\ICP\qgis\projects\minato-ku\minato-link.shp"
newLinkShapeFile = "C:\qgis\ICP\qgis\projects\minato-ku\minato-link-new.shp"
# linkShapeFile = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/minato-ku/minato-link.shp"
# nodeShapeFile = "C:\ICP\qgis\projects\minato-ku\minato-node.shp"
# nodeShapeFile = "/Users/HirokiSaitoRMC/home/QGIS/project/ICP/qgis/projects/minato-ku/minato-node.shp"
nodeShapeFile = "C:\qgis\ICP\qgis\projects\minato-ku\minato-node.shp"

# new objectid 30,000,000からスタート
newobjectid = 30000000

fromNodeLinks = {}
toNodeLinks = {}

# リンク接合時に値が同一であるべき属性
checkAttributes = ('roadcls_c', 'navicls_c', 'linkcls_c', 'width_c', 'nopass_c', 'oneway_c', 'lane_count', 'ts_drm_tri', 'legal_spee', 'legal_sp_1')


def check_attributes(f, t, attributes):

    for attr in attributes:
        if f['properties'][attr] != t['properties'][attr]:
            return False
        else:
            return True


def reverse_link(link):

    if link['properties']['oneway_c'] == 1:
        link['properties']['oneway_c'] = 3
    elif link['properties']['oneway_c'] == 3:
        link['properties']['oneway_c'] = 1
    elif link['properties']['oneway_c'] == 2:
        link['properties']['oneway_c'] = 4
    elif link['properties']['oneway_c'] == 4:
        link['properties']['oneway_c'] = 2

    if link['properties']['linkdir_c'] == 1:
        link['properties']['linkdir_c'] = 2
    elif link['properties']['linkdir_c'] == 2:
        link['properties']['linkdir_c'] = 1

    link['properties']['coordinates'] = link['properties']['coordinates'][::-1]
    return link


def merge_links(a, b, node):
    # 新しいobjectid
    global newobjectid
    if newobjectid is not 30000000:
        newobjectid = newobjectid = newobjectid + 1


    newa = a
    newb = b

    # ノードの位置を特定
    aNodes = (a['properties']['fromnodeid'], a['properties']['tonodeid'])
    bNodes = (b['properties']['fromnodeid'], b['properties']['tonodeid'])
    aNodePos = aNodes.index(node)
    bNodePos = bNodes.index(node)

    # coordinates
    newc = []
    ac = newa['geometry']['coordinates']
    bc = newb['geometry']['coordinates']

    # # 両リンクの向きを確認 同一方向に
    # # <-a- n -b->  =>  -a-> n -b->
    if aNodePos == 0 and bNodePos == 0:
        print("<-a- n -b->")
        a = reverse_link(a)
        bc.reverse()
        # shape
        for pos in bc:
            newc.extend(pos)
        newc.extend(ac)
        # from, to
        newfromnodeid = aNodes[1]
        newtonodeid = bNodes[1]

    # # -a-> n -b->
    elif aNodePos == 1 and bNodePos == 0:
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[1]
        newc.extend(ac)
        newc.extend(bc)
    # # <-a- n <-b-
    elif aNodePos == 0 and bNodePos == 1:
        newfromnodeid = bNodes[0]
        newtonodeid = aNodes[1]
        newc.extend(bc)
        newc.extend(ac)
    # # -a-> n <-b-  =>  -a-> n -b->
    elif aNodePos == 1 and bNodePos == 1:
        print("-a-> n <-b-")
        b = reverse_link(b)
        bc.reverse()
        # shape
        newc.extend(ac)
        for pos in bc:
            newc.extend(pos)
        newfromnodeid = aNodes[0]
        newtonodeid = bNodes[0]

    newa['properties']['objectid'] = newobjectid
    newa['properties']['fromnodeid'] = newfromnodeid
    newa['properties']['tonodeid'] = newtonodeid
    newa['geometry']['coordinates'] = newc
    return newa

def write_link_shape_file(f):
    with open(linkShapeFile, 'r') as source:
        with open(newLinkShapeFile, 'w', **source.meta) as sink:
            for f in source:
                try:
                    geom = shape(f['geometry'])
                    if not geom.is_valid:
                        geom = geom.buffer(0.0)
                    f['geometry'] = mapping(geom)
                    sink.write(f)

                except Exception:
                    print(f"Error on {f['properties']['objectid']}")

# リンクレイヤからfromnodeid, tonodeid を取得し、featureをList[objectid] 形式でリスト化　
with collection(linkShapeFile, "r") as fl:
    for feature in fl:
        fromNodeId = feature['properties']['fromnodeid']
        fromNodeLinks[fromNodeId] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}
        toNodeId = feature['properties']['tonodeid']
        toNodeLinks[toNodeId] = {'type': 'Feature', 'id': feature['id'], 'properties': feature['properties'], 'geometry': feature['geometry']}

    # connlink=2のノードに接続しているリンクを接合する
    with collection(nodeShapeFile, "r") as fn:
        with collection(newLinkShapeFile, 'w', **fl.meta) as f:
            for feature in fn:
                connlink = feature['properties']['connlink']
                if connlink == 2:
                    nodeId = feature['properties']['objectid']
                    # 接合対象のリンクを特定
                    if nodeId in fromNodeLinks.keys():
                        fromLink = fromNodeLinks.pop(nodeId)
                        print(f"fromLink:{fromLink}")
                        if nodeId in toNodeLinks.keys():
                            toLink = toNodeLinks.pop(nodeId)
                            if check_attributes(fromLink, toLink, checkAttributes):
                                newLink = merge_links(fromLink, toLink, nodeId)
                                fromLink[newLink['properties']['objectid']] = newLink
                                toLink[newLink['properties']['objectid']] = newLink
                                print(f"  toLink:{toLink}")
                                print(f" newLink:{newLink}")
                                try:

                                    # geom = shape(newLink['geometry'])
                                    # newLink['geometry'] = mapping(geom)

                                    f.write(newLink)

                                except Exception as e:
                                    print(f"Error on {newLink['properties']['objectid']} :{e}")




